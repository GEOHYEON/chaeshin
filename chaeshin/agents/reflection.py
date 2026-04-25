"""
ReflectionAgent — 피드백 → 그래프 변환 에이전트.

claw-code 참고:
- replan_graph: diff 기반 그래프 수정 (planner.py)
- 여기서는 유저 피드백을 LLM이 해석 → 그래프 변환 유형 결정 → 적용

역할:
1. 유저 피드백 수신 (자연어)
2. 피드백이 어느 레이어에 해당하는지 자동 판단
3. 해당 레이어의 Graph를 수정/분할/승격
4. chaeshin_retain으로 업데이트된 케이스 저장
5. 필요 시 difficulty 재산정

피드백 유형:
- ESCALATE: 기존 그래프를 한 레벨 아래로 밀고, 새 중간 레이어 생성
- MODIFY: 해당 레이어의 Graph에서 노드 순서/엣지 수정
- SIMPLIFY: 하위 레이어를 상위로 병합
- CORRECT: L1 Graph에서 tool 노드 교체
- REJECT: 해당 노드 제거 + 엣지 재연결
"""

from __future__ import annotations

import copy
import uuid
import structlog
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional

from chaeshin.agents.base import BaseAgent, AgentContext
from chaeshin.schema import (
    Case, CaseMetadata, ProblemFeatures, Solution, Outcome,
    ToolGraph, GraphNode, GraphEdge, ToolDef,
)
from chaeshin.planner import GraphPlanner, TaskTree


def _bump_layer(layer: str, delta: int) -> str:
    """레이어 라벨을 ±delta만큼 이동.

    "L1"+1 → "L2", "L2"-1 → "L1". 고정 3단계 가정 없음 — L4/L5도 자연스럽게 이동.
    파싱 실패하거나 결과가 0 이하면 "L1"로 폴백.
    """
    if not layer.startswith("L"):
        return "L1"
    try:
        n = int(layer[1:])
    except ValueError:
        return "L1"
    new = max(1, n + delta)
    return f"L{new}"
from chaeshin.case_store import CaseStore

logger = structlog.get_logger(__name__)


class ReflectionAgent(BaseAgent):
    """피드백 반영 에이전트.

    Orchestrator가 유저 피드백을 받으면 spawn.
    LLM이 피드백을 분석 → 그래프 변환 → Chaeshin에 저장.
    """

    def __init__(
        self,
        llm_fn: Callable[[List[Dict[str, str]]], Coroutine[Any, Any, str]],
        tools: Dict[str, ToolDef],
        case_store: Optional[CaseStore] = None,
        context: Optional[AgentContext] = None,
    ):
        super().__init__(
            agent_type="reflection",
            llm_fn=llm_fn,
            context=context,
        )
        self.planner = GraphPlanner(llm_fn=llm_fn, tools=tools)
        self.tools = tools
        self.case_store = case_store

    async def run(
        self,
        prompt: str,
        task_tree: Optional[TaskTree] = None,
        target_case_id: str = "",
        feedback_type: str = "auto",
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """피드백을 분석하고 그래프를 변환.

        Args:
            prompt: 유저 피드백 (자연어)
            task_tree: 현재 TaskTree (있으면)
            target_case_id: 피드백 대상 케이스 ID (있으면)
            feedback_type: auto/escalate/modify/simplify/correct/reject

        Yields:
            - {"type": "progress", "message": "피드백 분석 중..."}
            - {"type": "progress", "message": "ESCALATE 변환 수행 중..."}
            - {"type": "result", "output": {"type": "escalate", ...}}
        """
        yield {"type": "progress", "message": f"피드백 분석 중: {prompt[:50]}..."}

        # 대상 그래프 결정
        target_graph = None
        target_case = None

        if target_case_id and self.case_store:
            target_case = self.case_store.get_case_by_id(target_case_id)
            if target_case:
                target_graph = target_case.solution.tool_graph
        elif task_tree:
            target_graph = task_tree.graph

        if not target_graph:
            yield {"type": "error", "error": "피드백 대상 그래프를 찾을 수 없습니다"}
            return

        # LLM에게 피드백 분석 위임
        yield {"type": "progress", "message": "LLM에게 변환 방법 결정 위임 중..."}
        analysis = await self.planner.apply_feedback(
            target_graph, prompt, feedback_type,
        )

        resolved_type = analysis.get("type", feedback_type)
        yield {
            "type": "progress",
            "message": f"피드백 유형: {resolved_type.upper()} — {analysis.get('reasoning', '')}",
        }

        # 피드백 유형별 변환 수행
        if resolved_type == "escalate":
            result = await self._handle_escalate(
                target_graph, target_case, task_tree, analysis, prompt,
            )
        elif resolved_type == "modify":
            result = await self._handle_modify(
                target_graph, target_case, analysis, prompt,
            )
        elif resolved_type == "simplify":
            result = await self._handle_simplify(
                target_graph, target_case, task_tree, analysis, prompt,
            )
        elif resolved_type == "correct":
            result = await self._handle_correct(
                target_graph, target_case, analysis, prompt,
            )
        elif resolved_type == "reject":
            result = await self._handle_reject(
                target_graph, target_case, analysis, prompt,
            )
        else:
            # fallback → modify
            result = await self._handle_modify(
                target_graph, target_case, analysis, prompt,
            )

        # 피드백 기록
        if target_case_id and self.case_store:
            self.case_store.add_feedback(target_case_id, prompt, resolved_type)

        yield {
            "type": "result",
            "output": {
                "feedback_type": resolved_type,
                "reasoning": analysis.get("reasoning", ""),
                **result,
            },
        }

    async def _handle_escalate(
        self,
        graph: ToolGraph,
        case: Optional[Case],
        task_tree: Optional[TaskTree],
        analysis: Dict[str, Any],
        feedback: str,
    ) -> Dict[str, Any]:
        """ESCALATE: 기존 그래프를 하위로 밀고, 새 중간 레이어 생성.

        Before: L2 [A] → [B] → [C]
        After:  L2 (new) [X] → [Y] → [Z]
                L1 (demoted) [A] → [B] → [C]  (X의 child)
                L1 (new) [D] → [E]  (Y의 child)
        """
        # 기존 그래프를 한 레벨 아래로 강등
        demoted_graph = copy.deepcopy(graph)

        # 새 상위 레이어 생성 (LLM의 new_subtasks 기반)
        new_subtasks = analysis.get("new_subtasks", [])
        new_nodes = []
        new_edges = []

        for i, sub in enumerate(new_subtasks):
            node_id = f"esc_{i}"
            new_nodes.append(GraphNode(
                id=node_id,
                tool=sub.get("tool", "subtask"),
                note=sub.get("task", sub.get("note", "")),
            ))
            if i > 0:
                new_edges.append(GraphEdge(
                    from_node=f"esc_{i-1}", to_node=node_id,
                ))

        new_graph = ToolGraph(
            nodes=new_nodes,
            edges=new_edges,
            entry_nodes=[new_nodes[0].id] if new_nodes else [],
        )

        # Chaeshin에 저장
        saved_ids = {}
        if self.case_store and case:
            old_meta = case.metadata
            # 기존 케이스를 한 단계 아래로 — depth 기반 일반 계산.
            # 고정 L1/L2/L3 가정 없음. 깊이가 무제한이어도 작동.
            old_depth = getattr(old_meta, "depth", 0)
            old_layer = getattr(old_meta, "layer", "L1") or "L1"
            new_parent_depth = old_depth + 1
            new_parent_layer = _bump_layer(old_layer, +1)

            # 새 상위 케이스 생성 — pending 으로 저장. verdict는 사용자 권한.
            new_case_id = str(uuid.uuid4())
            new_case = Case(
                problem_features=ProblemFeatures(
                    request=f"{case.problem_features.request} (escalated: {feedback[:50]})",
                    category=case.problem_features.category,
                    keywords=case.problem_features.keywords,
                ),
                solution=Solution(tool_graph=new_graph),
                outcome=Outcome(status="pending"),
                metadata=CaseMetadata(
                    case_id=new_case_id,
                    layer=new_parent_layer,
                    depth=new_parent_depth,
                    difficulty=getattr(old_meta, "difficulty", 0) + 1,
                    child_case_ids=[old_meta.case_id],
                    source="reflection_escalate",
                ),
            )
            self.case_store.retain(new_case)
            self.case_store.link_parent_child(new_case_id, old_meta.case_id)
            saved_ids["new_parent"] = new_case_id
            saved_ids["demoted"] = old_meta.case_id

        return {
            "action": "escalate",
            "new_graph_nodes": len(new_nodes),
            "demoted_graph_nodes": len(demoted_graph.nodes),
            "saved_ids": saved_ids,
        }

    async def _handle_modify(
        self,
        graph: ToolGraph,
        case: Optional[Case],
        analysis: Dict[str, Any],
        feedback: str,
    ) -> Dict[str, Any]:
        """MODIFY: 노드 순서/엣지 수정."""
        diff = analysis.get("diff", {})
        if not diff:
            return {"action": "modify", "changes": 0, "note": "변경 사항 없음"}

        modified_graph = self.planner._apply_diff(graph, diff)

        # 케이스 업데이트
        if self.case_store and case:
            case.solution.tool_graph = modified_graph
            self.case_store.retain(case)

        changes = (
            len(diff.get("added_nodes", []))
            + len(diff.get("removed_nodes", []))
            + len(diff.get("added_edges", []))
            + len(diff.get("removed_edges", []))
            + len(diff.get("updated_nodes", []))
        )

        return {
            "action": "modify",
            "changes": changes,
            "modified_nodes": len(modified_graph.nodes),
            "modified_edges": len(modified_graph.edges),
        }

    async def _handle_simplify(
        self,
        graph: ToolGraph,
        case: Optional[Case],
        task_tree: Optional[TaskTree],
        analysis: Dict[str, Any],
        feedback: str,
    ) -> Dict[str, Any]:
        """SIMPLIFY: 하위 레이어를 상위로 병합."""
        if not task_tree or not task_tree.children:
            return {"action": "simplify", "note": "병합할 하위 레이어 없음"}

        # 모든 리프 노드를 현재 레이어에 flat하게 병합
        all_leaf_nodes = []
        for child in task_tree.children:
            for leaf in child.leaf_nodes():
                all_leaf_nodes.extend(leaf.graph.nodes)

        # 순차 엣지 생성
        merged_edges = []
        for i in range(1, len(all_leaf_nodes)):
            merged_edges.append(GraphEdge(
                from_node=all_leaf_nodes[i-1].id,
                to_node=all_leaf_nodes[i].id,
            ))

        merged_graph = ToolGraph(
            nodes=all_leaf_nodes,
            edges=merged_edges,
            entry_nodes=[all_leaf_nodes[0].id] if all_leaf_nodes else [],
        )

        # 케이스 업데이트
        if self.case_store and case:
            case.solution.tool_graph = merged_graph
            meta = case.metadata
            meta.difficulty = max(0, getattr(meta, "difficulty", 1) - 1)
            meta.child_case_ids = []  # 자식 제거
            self.case_store.retain(case)

        return {
            "action": "simplify",
            "merged_nodes": len(all_leaf_nodes),
            "layers_removed": 1,
        }

    async def _handle_correct(
        self,
        graph: ToolGraph,
        case: Optional[Case],
        analysis: Dict[str, Any],
        feedback: str,
    ) -> Dict[str, Any]:
        """CORRECT: 노드의 tool 교체."""
        updated_nodes = analysis.get("diff", {}).get("updated_nodes", [])
        corrections = 0

        for update in updated_nodes:
            node_id = update.get("id", "")
            new_tool = update.get("tool", "")
            if not node_id or not new_tool:
                continue

            node = graph.get_node(node_id)
            if node:
                old_tool = node.tool
                node.tool = new_tool
                corrections += 1
                logger.info("tool_corrected", node=node_id, old=old_tool, new=new_tool)

        if self.case_store and case and corrections > 0:
            self.case_store.retain(case)

        return {
            "action": "correct",
            "corrections": corrections,
        }

    async def _handle_reject(
        self,
        graph: ToolGraph,
        case: Optional[Case],
        analysis: Dict[str, Any],
        feedback: str,
    ) -> Dict[str, Any]:
        """REJECT: 노드 제거 + 엣지 재연결."""
        removed_ids = set(analysis.get("diff", {}).get("removed_nodes", []))
        if not removed_ids:
            return {"action": "reject", "removed": 0}

        # 노드 제거
        graph.nodes = [n for n in graph.nodes if n.id not in removed_ids]

        # 엣지 재연결 — 제거된 노드를 건너뛰는 새 엣지 생성
        new_edges = []
        for edge in graph.edges:
            if edge.from_node in removed_ids and edge.to_node in removed_ids:
                continue  # 양쪽 다 제거됨 → 엣지 삭제
            elif edge.from_node in removed_ids:
                # from이 제거됨 → 이 노드로 들어오던 엣지의 from을 연결
                incoming = [e for e in graph.edges if e.to_node == edge.from_node]
                for inc in incoming:
                    if inc.from_node not in removed_ids:
                        new_edges.append(GraphEdge(
                            from_node=inc.from_node,
                            to_node=edge.to_node,
                        ))
            elif edge.to_node and edge.to_node in removed_ids:
                # to가 제거됨 → 이 노드에서 나가던 엣지의 to를 연결
                outgoing = [e for e in graph.edges if e.from_node == edge.to_node]
                for out in outgoing:
                    if out.to_node and out.to_node not in removed_ids:
                        new_edges.append(GraphEdge(
                            from_node=edge.from_node,
                            to_node=out.to_node,
                        ))
            else:
                new_edges.append(edge)

        graph.edges = new_edges

        if self.case_store and case:
            self.case_store.retain(case)

        return {
            "action": "reject",
            "removed": len(removed_ids),
            "remaining_nodes": len(graph.nodes),
        }
