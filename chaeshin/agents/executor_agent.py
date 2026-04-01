"""
ExecutorAgent — 레이어별 실행 에이전트.

claw-code 참고:
- toolOrchestration.ts: concurrent-safe/serial 분류 후 배치 실행
- StreamingToolExecutor: 도구 실행 상태 추적 (queued→executing→completed)
- query.ts의 runTools: 도구 결과를 스트리밍으로 yield

역할:
1. 분해 트리의 최하위(L1)부터 Tool Call 실행
2. 레이어 완료 시 유저에게 체크포인트 보고
3. 실행 중 예외 → Planner에 replan 위임
4. 전체 실행 완료 → 결과 반환
"""

from __future__ import annotations

import structlog
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional

from chaeshin.agents.base import BaseAgent, AgentContext
from chaeshin.schema import ToolDef, ExecutionContext, NodeStatus
from chaeshin.graph_executor import GraphExecutor
from chaeshin.planner import TaskTree

logger = structlog.get_logger(__name__)


class ExecutorAgent(BaseAgent):
    """레이어별 실행 에이전트.

    Orchestrator가 DecomposerAgent 결과(TaskTree)를 받아서 spawn.
    GraphExecutor.execute_layered()를 감싸되, AsyncGenerator로
    중간 진행을 스트리밍.
    """

    def __init__(
        self,
        tools: Dict[str, ToolDef],
        llm_fn: Optional[Callable[[List[Dict[str, str]]], Coroutine[Any, Any, str]]] = None,
        on_replan: Optional[Callable] = None,
        context: Optional[AgentContext] = None,
    ):
        super().__init__(
            agent_type="executor",
            llm_fn=llm_fn,
            context=context,
        )
        self.graph_executor = GraphExecutor(
            tools=tools,
            on_replan=on_replan,
        )
        self.tools = tools

    async def run(
        self,
        prompt: str,
        task_tree: Optional[TaskTree] = None,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """태스크 트리를 레이어별로 실행.

        Args:
            prompt: 실행 설명 (로그용)
            task_tree: DecomposerAgent가 만든 TaskTree

        Yields:
            - {"type": "progress", "message": "L1 실행 중..."}
            - {"type": "checkpoint", "layer": "L1", "results": [...]}
            - {"type": "tool_executed", "node_id": "...", "tool": "...", "status": "done"}
            - {"type": "result", "output": {"completed": True, ...}}
        """
        if not task_tree:
            yield {"type": "error", "error": "task_tree가 필요합니다"}
            return

        yield {
            "type": "progress",
            "message": f"실행 시작 — 난이도 {task_tree.difficulty}, "
                       f"리프 노드 {len(task_tree.leaf_nodes())}개",
        }

        # 레이어별 bottom-up 수집
        execution_order = self.graph_executor._build_execution_order(task_tree)
        all_results: Dict[str, Any] = {
            "layers": [],
            "total_tools_run": 0,
            "completed": False,
        }

        for layer_name, trees_in_layer in execution_order:
            yield {
                "type": "progress",
                "message": f"{layer_name} 레이어 실행 중 ({len(trees_in_layer)}개 태스크)...",
            }

            layer_results = []

            for tree in trees_in_layer:
                if tree.is_leaf and tree.graph.nodes:
                    # L1 최하위 — 실제 tool call 실행
                    ctx = await self.graph_executor.execute(tree.graph)
                    tools_run = sum(
                        1 for ns in ctx.node_states.values()
                        if ns.status == NodeStatus.DONE
                    )
                    all_results["total_tools_run"] += tools_run

                    # 각 노드 실행 결과를 개별 yield
                    for nid, ns in ctx.node_states.items():
                        node = tree.graph.get_node(nid)
                        yield {
                            "type": "tool_executed",
                            "node_id": nid,
                            "tool": node.tool if node else "unknown",
                            "status": ns.status.value,
                            "output_preview": str(ns.output_data)[:200] if ns.output_data else None,
                            "error": ns.error,
                        }

                    layer_results.append({
                        "request": tree.request,
                        "completed": ctx.completed,
                        "tools_run": tools_run,
                    })
                else:
                    # 상위 레이어 — 하위 결과 종합
                    layer_results.append({
                        "request": tree.request,
                        "aggregated": True,
                        "children": len(tree.children),
                    })

            all_results["layers"].append({
                "layer": layer_name,
                "results": layer_results,
            })

            # 체크포인트 — 유저에게 중간 보고
            remaining = len(execution_order) - len(all_results["layers"])
            yield {
                "type": "checkpoint",
                "layer": layer_name,
                "tasks_done": len(layer_results),
                "remaining_layers": remaining,
                "total_tools_so_far": all_results["total_tools_run"],
            }

        all_results["completed"] = True

        yield {
            "type": "result",
            "output": all_results,
        }
