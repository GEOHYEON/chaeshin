"""
OrchestratorAgent — 대화 루프 + 서브에이전트 디스패치.

claw-code 참고:
- QueryEngine.ts: 전체 대화 라이프사이클 관리
- query.ts queryLoop: while(true) { API 호출 → tool 실행 → stop_reason 판단 }
- AgentTool: 서브에이전트 spawn (subagent_type, prompt, isolation)
- forkSubagent: 부모 컨텍스트 상속, 캐시 동일 tool 정의

역할:
1. 유저 질문 수신
2. 난이도 판단 (쉬우면 바로 실행, 어려우면 Decomposer에 위임)
3. Decomposer → Executor → 유저 체크포인트 루프
4. 유저 피드백 → Reflection Agent 위임
5. 완료 후 chaeshin_retain으로 케이스 저장

핵심 흐름:
    while True:
        유저 메시지 수신
        ├─ 쉬운 질문 → 바로 tool call
        ├─ 어려운 질문 → Decomposer spawn → TaskTree
        │   └─ Executor spawn → 레이어별 실행
        │       └─ 체크포인트마다 유저 확인
        │           ├─ "계속" → 다음 레이어
        │           ├─ "수정" → Reflection spawn
        │           └─ "중단" → 중단
        └─ 피드백 → Reflection spawn
"""

from __future__ import annotations

import structlog
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional

from chaeshin.agents.base import BaseAgent, SubagentManager, AgentContext, AgentResult
from chaeshin.agents.decomposer import DecomposerAgent
from chaeshin.agents.executor_agent import ExecutorAgent
from chaeshin.agents.reflection import ReflectionAgent
from chaeshin.schema import (
    Case, CaseMetadata, ProblemFeatures, Solution, Outcome,
    ToolDef, ToolGraph,
)
from chaeshin.case_store import CaseStore
from chaeshin.planner import TaskTree

logger = structlog.get_logger(__name__)


class OrchestratorAgent(BaseAgent):
    """대화 루프 총괄 에이전트.

    claw-code의 QueryEngine + queryLoop을 합친 구조.
    유저 질문을 받으면 난이도를 판단하고,
    적절한 서브에이전트를 spawn하여 처리.
    """

    def __init__(
        self,
        llm_fn: Callable[[List[Dict[str, str]]], Coroutine[Any, Any, str]],
        tools: Dict[str, ToolDef],
        case_store: Optional[CaseStore] = None,
        context: Optional[AgentContext] = None,
        # 설정
        difficulty_threshold: int = 2,
        feedback_count_threshold: int = 3,
        auto_retain: bool = True,
    ):
        super().__init__(
            agent_type="orchestrator",
            llm_fn=llm_fn,
            context=context,
        )
        self.tools = tools
        self.case_store = case_store
        self.manager = SubagentManager()

        # 설정
        self.difficulty_threshold = difficulty_threshold
        self.feedback_count_threshold = feedback_count_threshold
        self.auto_retain = auto_retain

        # 현재 세션 상태
        self._current_tree: Optional[TaskTree] = None
        self._conversation: List[Dict[str, str]] = []

    async def run(
        self,
        prompt: str,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """단일 질문 처리 — 분해 → 실행 → 결과 반환.

        Args:
            prompt: 유저 질문

        Yields:
            진행 상황 + 체크포인트 + 최종 결과
        """
        self._conversation.append({"role": "user", "content": prompt})

        yield {"type": "progress", "message": f"질문 접수: {prompt[:60]}..."}

        # 1단계: 난이도 사전 판단
        difficulty_estimate = await self._estimate_difficulty(prompt)

        yield {
            "type": "progress",
            "message": f"난이도 추정: {difficulty_estimate['level']} "
                       f"({difficulty_estimate['reason']})",
        }

        if difficulty_estimate["level"] == "easy":
            # 쉬운 질문 → Chaeshin 조회 없이 바로 처리
            async for event in self._handle_easy(prompt, **kwargs):
                yield event
        else:
            # 어려운 질문 → Decomposer → Executor 파이프라인
            async for event in self._handle_complex(prompt, **kwargs):
                yield event

    async def _estimate_difficulty(self, query: str) -> Dict[str, Any]:
        """질문 난이도 사전 추정.

        두 축:
        1. Chaeshin에 유사 케이스가 있고 difficulty >= threshold
        2. Chaeshin에 유사 케이스가 있고 feedback_count >= threshold
        3. 없으면 LLM에게 간단 판단 위임
        """
        # Chaeshin 기반 판단
        if self.case_store:
            problem = ProblemFeatures(request=query, category="", keywords=[])
            results = self.case_store.retrieve(problem, top_k=3)

            for case, score in results:
                if score < 0.4:
                    continue
                meta = case.metadata
                diff = getattr(meta, "difficulty", 0)
                fb = getattr(meta, "feedback_count", 0)

                if diff >= self.difficulty_threshold:
                    return {
                        "level": "hard",
                        "reason": f"유사 케이스 difficulty={diff} (임계값={self.difficulty_threshold})",
                        "matched_case_id": meta.case_id,
                    }
                if fb >= self.feedback_count_threshold:
                    return {
                        "level": "hard",
                        "reason": f"유사 케이스 feedback_count={fb} (임계값={self.feedback_count_threshold})",
                        "matched_case_id": meta.case_id,
                    }

        # LLM 기반 판단 (Chaeshin에 정보 없을 때)
        messages = [
            {"role": "system", "content": (
                "당신은 질문의 복잡도를 판단합니다.\n"
                f"사용 가능한 도구: {', '.join(self.tools.keys())}\n\n"
                "이 질문이 도구 1~2개로 바로 해결 가능하면 'easy',\n"
                "여러 단계의 분해가 필요하면 'hard'로 답하세요.\n"
                "JSON만 출력: {\"level\": \"easy|hard\", \"reason\": \"이유\"}"
            )},
            {"role": "user", "content": query},
        ]

        try:
            import json
            response = await self._call_llm(messages)
            parsed = json.loads(self._extract_json_safe(response))
            return {
                "level": parsed.get("level", "hard"),
                "reason": parsed.get("reason", "LLM 판단"),
            }
        except Exception:
            # 판단 실패 → 안전하게 hard로
            return {"level": "hard", "reason": "판단 실패 — 안전하게 복잡으로 처리"}

    async def _handle_easy(
        self, prompt: str, **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """쉬운 질문 처리 — Chaeshin 조회 없이 직접 그래프 생성 + 실행."""
        from chaeshin.planner import GraphPlanner

        yield {"type": "progress", "message": "쉬운 질문 — 직접 그래프 생성 중..."}

        planner = GraphPlanner(llm_fn=self.llm_fn, tools=self.tools)
        problem = ProblemFeatures(request=prompt, category="", keywords=[])

        graph = await planner.create_graph(problem)

        yield {
            "type": "progress",
            "message": f"그래프 생성 완료 — 노드 {len(graph.nodes)}개",
        }

        # 직접 실행
        from chaeshin.graph_executor import GraphExecutor
        executor = GraphExecutor(tools=self.tools)
        ctx = await executor.execute(graph)

        # 결과 수집
        results = {}
        for nid, ns in ctx.node_states.items():
            node = graph.get_node(nid)
            results[nid] = {
                "tool": node.tool if node else "unknown",
                "status": ns.status.value,
                "output": ns.output_data,
            }

        # 자동 retain — 항상 pending. 성공/실패는 사용자 verdict로만 결정됨.
        if self.auto_retain and self.case_store:
            case = Case(
                problem_features=problem,
                solution=Solution(tool_graph=graph),
                outcome=Outcome(
                    status="pending",
                    tools_executed=len(graph.nodes),
                ),
                metadata=CaseMetadata(
                    source="orchestrator",
                    layer="L1",
                    depth=0,
                ),
            )
            self.case_store.retain(case)

        yield {
            "type": "result",
            "output": {
                "mode": "easy",
                "completed": ctx.completed,
                "results": results,
            },
        }

    async def _handle_complex(
        self, prompt: str, **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """복잡한 질문 처리 — Decomposer → Executor 파이프라인."""

        # ── Phase 1: Decomposer ──
        yield {"type": "progress", "message": "Decomposer 에이전트 생성 중..."}

        decomposer = DecomposerAgent(
            llm_fn=self.llm_fn,
            tools=self.tools,
            case_store=self.case_store,
        )

        decompose_result = None
        async for event in self.manager.spawn_streaming(decomposer, prompt):
            yield event
            if event.get("type") == "result":
                decompose_result = event.get("output", {})

        if not decompose_result or "task_tree" not in decompose_result:
            yield {"type": "error", "error": "Decomposer가 태스크 트리를 생성하지 못했습니다"}
            return

        task_tree = decompose_result["task_tree"]
        self._current_tree = task_tree

        yield {
            "type": "progress",
            "message": f"분해 완료 — 난이도 {task_tree.difficulty}, "
                       f"리프 {len(task_tree.leaf_nodes())}개",
        }

        # ── Phase 2: Executor ──
        yield {"type": "progress", "message": "Executor 에이전트 생성 중..."}

        executor_agent = ExecutorAgent(
            tools=self.tools,
            llm_fn=self.llm_fn,
        )

        execution_result = None
        async for event in self.manager.spawn_streaming(
            executor_agent, prompt, task_tree=task_tree,
        ):
            yield event
            if event.get("type") == "result":
                execution_result = event.get("output", {})

        # ── Phase 3: Auto-retain ──
        if self.auto_retain and self.case_store and task_tree:
            await self._retain_tree(task_tree, prompt)
            yield {"type": "progress", "message": "실행 패턴 Chaeshin에 저장 완료"}

        yield {
            "type": "result",
            "output": {
                "mode": "complex",
                "task_tree": task_tree.to_dict(),
                "execution": execution_result,
            },
        }

    async def handle_feedback(
        self,
        feedback: str,
        target_case_id: str = "",
        feedback_type: str = "auto",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """유저 피드백 처리 — Reflection Agent에 위임.

        Orchestrator 외부에서 호출 (대화 루프에서 피드백 감지 시).
        """
        yield {"type": "progress", "message": "Reflection 에이전트 생성 중..."}

        reflection = ReflectionAgent(
            llm_fn=self.llm_fn,
            tools=self.tools,
            case_store=self.case_store,
        )

        async for event in self.manager.spawn_streaming(
            reflection,
            feedback,
            task_tree=self._current_tree,
            target_case_id=target_case_id,
            feedback_type=feedback_type,
        ):
            yield event

    async def _retain_tree(self, tree: TaskTree, original_request: str):
        """TaskTree를 Chaeshin에 계층적으로 저장.

        모든 케이스는 pending으로 저장된다. 성공/실패는 나중에 사용자가
        chaeshin_verdict로 명시적으로 결정한다.
        """
        if not self.case_store:
            return

        # depth = 자식이 없으면 0(leaf), 있으면 자식의 max depth + 1
        depth = 0
        if tree.children:
            depth = 1  # 일단 1, 자식 처리 후 재계산
        case = Case(
            problem_features=ProblemFeatures(
                request=original_request,
                category="",
                keywords=[],
            ),
            solution=Solution(tool_graph=tree.graph),
            outcome=Outcome(status="pending"),
            metadata=CaseMetadata(
                source="orchestrator",
                layer=tree.layer or "L1",
                depth=depth,
                difficulty=tree.difficulty,
            ),
        )
        case_id = self.case_store.retain(case)
        tree.case_id = case_id

        # 재귀적으로 자식들도 저장
        child_ids = []
        for child in tree.children:
            await self._retain_tree(child, child.request)
            child_ids.append(child.case_id)

        # 부모-자식 링크
        if child_ids:
            case.metadata.child_case_ids = child_ids
            for child_id in child_ids:
                self.case_store.link_parent_child(case_id, child_id)

    @staticmethod
    def _extract_json_safe(text: str) -> str:
        """텍스트에서 JSON 추출 (안전)."""
        import re
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return match.group(0) if match else "{}"

    # ── Convenience: Interactive Loop ──────────────────────────────────

    async def interactive_loop(
        self,
        input_fn: Callable[[], Coroutine[Any, Any, str]],
        output_fn: Callable[[str], Coroutine[Any, Any, None]],
    ):
        """인터랙티브 대화 루프 — CLI나 웹 UI에서 사용.

        claw-code의 main.tsx 진입점 패턴:
        while True:
            user_input = await input_fn()
            async for event in orchestrator.run(user_input):
                await output_fn(format(event))

        Args:
            input_fn: 유저 입력 받기 (async)
            output_fn: 출력 보내기 (async)
        """
        await output_fn("Chaeshin Agent 시작. 'quit'으로 종료.\n")

        while True:
            user_input = await input_fn()

            if user_input.strip().lower() in ("quit", "exit", "q"):
                await output_fn("세션 종료.\n")
                break

            # 피드백 감지 (간단한 규칙 기반)
            if user_input.startswith("/feedback "):
                feedback_text = user_input[len("/feedback "):]
                async for event in self.handle_feedback(feedback_text):
                    await self._format_and_output(event, output_fn)
                continue

            # 일반 질문 처리
            async for event in self.run(user_input):
                await self._format_and_output(event, output_fn)

            await output_fn("\n---\n")

    @staticmethod
    async def _format_and_output(
        event: Dict[str, Any],
        output_fn: Callable[[str], Coroutine[Any, Any, None]],
    ):
        """이벤트를 사람이 읽을 수 있는 형식으로 변환."""
        etype = event.get("type", "unknown")

        if etype == "progress":
            await output_fn(f"⏳ {event.get('message', '')}\n")
        elif etype == "checkpoint":
            layer = event.get("layer", "?")
            remaining = event.get("remaining_layers", 0)
            await output_fn(
                f"✅ {layer} 완료 (남은 레이어: {remaining})\n"
            )
        elif etype == "tool_executed":
            tool = event.get("tool", "?")
            status = event.get("status", "?")
            symbol = "✓" if status == "done" else "✗"
            await output_fn(f"  {symbol} {tool}: {status}\n")
        elif etype == "result":
            import json
            output = event.get("output", {})
            mode = output.get("mode", "unknown")
            await output_fn(f"\n🎯 완료 (모드: {mode})\n")
        elif etype == "error":
            await output_fn(f"❌ 오류: {event.get('error', '?')}\n")
