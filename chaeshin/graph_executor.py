"""
Graph Executor — Tool Graph 실행 엔진.

그래프(설계도)는 불변. 실행 컨텍스트(커서)만 움직임.
방식 C (하이브리드): 정상 진행은 코드가 자동 처리, 예외 시 LLM에 위임.

요리로 비유하면: 레시피대로 요리를 진행하는 실행자.
"다음 단계는 뭐지?" → 레시피(그래프)를 보고 결정.
"간이 싱거운데?" → 레시피의 조건을 보고 자동 분기.
"전화 와서 탔는데?" → 셰프(LLM)에게 판단 위임.
"""

from __future__ import annotations

import asyncio
import json
import re
import structlog
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from chaeshin.schema import (
    ToolGraph,
    GraphNode,
    GraphEdge,
    ExecutionContext,
    NodeState,
    NodeStatus,
    ToolDef,
)

logger = structlog.get_logger(__name__)


class GraphExecutor:
    """Tool Graph 실행 엔진.

    1. CBR에서 가져온 그래프(불변)를 받음
    2. 실행 컨텍스트를 만들어 커서를 움직임
    3. 각 노드에서 tool을 실행하고 결과를 기록
    4. edge condition을 평가해 다음 노드를 결정
    5. 코드로 판단 안 되면 on_replan 콜백으로 LLM에 위임
    """

    def __init__(
        self,
        tools: Dict[str, ToolDef],
        on_node_start: Optional[Callable] = None,
        on_node_end: Optional[Callable] = None,
        on_replan: Optional[Callable] = None,
        on_special_action: Optional[Callable] = None,
        on_patient_todo_update: Optional[Callable] = None,
    ):
        self.tools = tools  # name → ToolDef
        self.on_node_start = on_node_start  # async (node, ctx) → None
        self.on_node_end = on_node_end  # async (node, ctx, result) → None
        self.on_replan = on_replan  # async (graph, ctx, reason) → ToolGraph (수정된 그래프)
        self.on_special_action = on_special_action  # async (action, ctx) → Any
        self.on_patient_todo_update = on_patient_todo_update  # async (todo_items) → None

    async def execute(
        self,
        graph: ToolGraph,
        context: Optional[ExecutionContext] = None,
        initial_input: Optional[Dict[str, Any]] = None,
    ) -> ExecutionContext:
        """그래프 실행 — 메인 루프.

        Args:
            graph: 실행할 Tool Graph (CBR에서 가져온 설계도)
            context: 기존 실행 컨텍스트 (이어서 실행할 때)
            initial_input: 초기 입력 데이터

        Returns:
            완료된 ExecutionContext
        """
        ctx = context or ExecutionContext()

        # 초기화: 모든 노드를 PENDING으로
        if not ctx.node_states:
            for node in graph.nodes:
                ctx.node_states[node.id] = NodeState(node_id=node.id)

            # entry 노드를 READY로
            entry_nodes = graph.entry_nodes or self._find_entry_nodes(graph)
            for nid in entry_nodes:
                ctx.get_node_state(nid).status = NodeStatus.READY
                if initial_input:
                    ctx.get_node_state(nid).input_data = initial_input

        # 환자 TODO 초기 생성
        await self._update_patient_todo(graph, ctx)

        # 메인 루프
        while not ctx.completed:
            # READY 노드 찾기
            ready_nodes = self._get_ready_nodes(ctx)

            if not ready_nodes:
                # 실행할 노드가 없음 → 완료 또는 교착
                if self._all_done_or_skipped(ctx):
                    ctx.completed = True
                    break
                else:
                    # 교착 상태 → LLM에 리플래닝 위임
                    logger.warning("deadlock_detected", ctx=ctx.session_id)
                    graph = await self._request_replan(
                        graph, ctx, "교착 상태: 실행 가능한 노드가 없음"
                    )
                    continue

            # 병렬 그룹 체크 — 동시 실행 가능한 노드는 병렬로
            parallel, sequential = self._classify_ready_nodes(
                ready_nodes, graph.parallel_groups
            )

            # 병렬 실행
            if parallel:
                tasks = [
                    self._execute_node(graph, ctx, nid) for nid in parallel
                ]
                await asyncio.gather(*tasks)

            # 순차 실행
            for nid in sequential:
                result = await self._execute_node(graph, ctx, nid)

                # 특수 액션 체크 (emergency_exit, ask_user 등)
                if ctx.special_action:
                    if self.on_special_action:
                        await self.on_special_action(ctx.special_action, ctx)
                    ctx.completed = True
                    break

            # 환자 TODO 업데이트
            await self._update_patient_todo(graph, ctx)

        ctx.record_event("execution_completed", "", {"completed": ctx.completed})
        return ctx

    async def _execute_node(
        self,
        graph: ToolGraph,
        ctx: ExecutionContext,
        node_id: str,
    ) -> Dict[str, Any]:
        """단일 노드 실행."""
        node = graph.get_node(node_id)
        ns = ctx.get_node_state(node_id)

        # 상태 전이: READY → RUNNING
        ns.status = NodeStatus.RUNNING
        ns.started_at = datetime.now().isoformat()
        ctx.current_nodes = [node_id]
        ctx.record_event("node_started", node_id)

        if self.on_node_start:
            await self.on_node_start(node, ctx)

        # 도구 실행
        tool_def = self.tools.get(node.tool)
        if not tool_def or not tool_def.executor:
            ns.status = NodeStatus.FAILED
            ns.error = f"도구를 찾을 수 없음: {node.tool}"
            ns.finished_at = datetime.now().isoformat()
            ctx.record_event("node_failed", node_id, {"error": ns.error})
            return {}

        try:
            # params_hint + input_data를 합쳐서 인자 구성
            args = {**node.params_hint, **ns.input_data}
            result_str = await tool_def.executor(args)

            # 결과 파싱
            try:
                result = json.loads(result_str) if isinstance(result_str, str) else result_str
            except json.JSONDecodeError:
                result = {"raw": result_str}

            ns.output_data = result
            ns.status = NodeStatus.DONE
            ns.finished_at = datetime.now().isoformat()
            ctx.record_event("node_completed", node_id, {"output": result})

            if self.on_node_end:
                await self.on_node_end(node, ctx, result)

        except Exception as e:
            ns.status = NodeStatus.FAILED
            ns.error = str(e)
            ns.finished_at = datetime.now().isoformat()
            ctx.record_event("node_failed", node_id, {"error": str(e)})
            logger.error("node_execution_error", node=node_id, error=str(e))

            # 실패 시 LLM에 리플래닝 위임
            graph = await self._request_replan(
                graph, ctx, f"노드 {node_id}({node.tool}) 실행 실패: {e}"
            )
            return {}

        # 다음 노드 결정
        await self._advance(graph, ctx, node_id)

        return result

    async def _advance(
        self,
        graph: ToolGraph,
        ctx: ExecutionContext,
        completed_node_id: str,
    ):
        """완료된 노드에서 다음 노드(들)를 결정.

        edge의 condition을 평가해서 다음 갈 곳을 찾음.
        매칭되는 edge가 없으면 LLM에 리플래닝 위임.
        """
        outgoing = graph.get_outgoing_edges(completed_node_id)

        if not outgoing:
            # 나가는 엣지가 없음 = 이 경로의 종점
            return

        matched = False
        for edge in outgoing:
            if self._evaluate_condition(edge.condition, ctx):
                matched = True

                if edge.to_node is None:
                    # 특수 액션 (emergency_exit, ask_user 등)
                    ctx.special_action = edge.action
                    # 나머지 PENDING 노드를 SKIPPED로
                    for nid, ns in ctx.node_states.items():
                        if ns.status in (NodeStatus.PENDING, NodeStatus.READY):
                            ns.status = NodeStatus.SKIPPED
                    return

                # 다음 노드를 READY로
                next_ns = ctx.get_node_state(edge.to_node)

                # 루프 체크
                if next_ns.status == NodeStatus.DONE:
                    if next_ns.loop_count >= graph.max_loops:
                        logger.warning(
                            "max_loop_reached",
                            node=edge.to_node,
                            count=next_ns.loop_count,
                        )
                        continue  # 다음 edge 시도
                    next_ns.loop_count += 1
                    ctx.record_event(
                        "loop_triggered", edge.to_node,
                        {"loop_count": next_ns.loop_count},
                    )

                next_ns.status = NodeStatus.READY

                # 이전 노드의 output을 다음 노드의 input으로 전달
                prev_output = ctx.get_node_state(completed_node_id).output_data
                next_ns.input_data.update(prev_output)

                break  # 첫 번째 매칭 edge만 실행 (priority 순)

        if not matched:
            # 매칭되는 edge가 없음 → 예상 못한 상황 → LLM에 위임
            logger.warning(
                "no_matching_edge",
                node=completed_node_id,
                output=ctx.get_node_state(completed_node_id).output_data,
            )
            graph = await self._request_replan(
                graph, ctx,
                f"노드 {completed_node_id} 완료 후 매칭되는 edge 없음. "
                f"output: {ctx.get_node_state(completed_node_id).output_data}"
            )

    def _evaluate_condition(
        self,
        condition: Optional[str],
        ctx: ExecutionContext,
    ) -> bool:
        """edge condition 평가.

        condition 형식: "n1.output.field == value"
        condition이 None이면 무조건 True (기본 경로).
        """
        if condition is None:
            return True

        try:
            # "n1.output.red_flag_detected == false" 파싱
            match = re.match(
                r"(\w+)\.output\.(\w+)\s*(==|!=|>=|<=|>|<)\s*(.+)",
                condition.strip(),
            )
            if not match:
                logger.warning("unparseable_condition", condition=condition)
                return False

            node_id, field, operator, expected = match.groups()
            expected = expected.strip().strip("'\"")

            # 노드 output에서 값 가져오기
            ns = ctx.node_states.get(node_id)
            if not ns or not ns.output_data:
                return False

            actual = ns.output_data.get(field)
            if actual is None:
                return False

            # 타입 변환
            actual_str = str(actual).lower()
            expected_lower = expected.lower()

            # 비교
            if operator == "==":
                return actual_str == expected_lower
            elif operator == "!=":
                return actual_str != expected_lower
            elif operator in (">", ">=", "<", "<="):
                try:
                    a, e = float(actual), float(expected)
                    if operator == ">":
                        return a > e
                    elif operator == ">=":
                        return a >= e
                    elif operator == "<":
                        return a < e
                    elif operator == "<=":
                        return a <= e
                except ValueError:
                    return False

            return False

        except Exception as e:
            logger.error("condition_eval_error", condition=condition, error=str(e))
            return False

    async def _request_replan(
        self,
        graph: ToolGraph,
        ctx: ExecutionContext,
        reason: str,
    ) -> ToolGraph:
        """LLM에 리플래닝 위임 (방식 C의 핵심).

        코드로 처리 못하는 상황에서만 호출됨.
        """
        if self.on_replan:
            logger.info("requesting_replan", reason=reason)
            ctx.record_event("replan_requested", "", {"reason": reason})
            new_graph = await self.on_replan(graph, ctx, reason)
            if new_graph:
                ctx.graph_version += 1
                ctx.record_event(
                    "graph_updated", "",
                    {"version": ctx.graph_version, "reason": reason},
                )
                return new_graph
        return graph

    def _find_entry_nodes(self, graph: ToolGraph) -> List[str]:
        """진입 노드 자동 탐지 — 들어오는 엣지가 없는 노드."""
        targets = {e.to_node for e in graph.edges if e.to_node}
        return [n.id for n in graph.nodes if n.id not in targets]

    def _get_ready_nodes(self, ctx: ExecutionContext) -> List[str]:
        return [
            nid for nid, ns in ctx.node_states.items()
            if ns.status == NodeStatus.READY
        ]

    def _all_done_or_skipped(self, ctx: ExecutionContext) -> bool:
        return all(
            ns.status in (NodeStatus.DONE, NodeStatus.SKIPPED, NodeStatus.FAILED)
            for ns in ctx.node_states.values()
        )

    def _classify_ready_nodes(
        self,
        ready: List[str],
        parallel_groups: List[List[str]],
    ) -> Tuple[List[str], List[str]]:
        """READY 노드를 병렬/순차로 분류."""
        parallel = []
        for group in parallel_groups:
            group_ready = [nid for nid in group if nid in ready]
            if len(group_ready) > 1:
                parallel.extend(group_ready)

        sequential = [nid for nid in ready if nid not in parallel]
        return parallel, sequential

    async def _update_patient_todo(
        self, graph: ToolGraph, ctx: ExecutionContext,
    ):
        """환자 TODO 동적 생성 — tool_graph + execution context에서 생성."""
        if not self.on_patient_todo_update:
            return

        items = []
        for node in graph.nodes:
            ns = ctx.get_node_state(node.id)
            tool_def = self.tools.get(node.tool)
            display = tool_def.display_name if tool_def else node.tool

            # 같은 display_name의 노드가 이미 있으면 병합
            existing = next((i for i in items if i["label"] == display), None)
            if existing:
                existing["node_ids"].append(node.id)
                # 상태 우선순위: running > ready > pending > done > skipped
                if ns.status == NodeStatus.RUNNING:
                    existing["status"] = "running"
                elif ns.status == NodeStatus.DONE and existing["status"] != "running":
                    existing["status"] = "done"
            else:
                status_map = {
                    NodeStatus.PENDING: "pending",
                    NodeStatus.READY: "ready",
                    NodeStatus.RUNNING: "running",
                    NodeStatus.DONE: "done",
                    NodeStatus.FAILED: "failed",
                    NodeStatus.SKIPPED: "skipped",
                }
                items.append({
                    "label": display,
                    "status": status_map.get(ns.status, "pending"),
                    "node_ids": [node.id],
                })

        await self.on_patient_todo_update(items)
