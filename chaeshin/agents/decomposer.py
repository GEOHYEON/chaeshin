"""
DecomposerAgent — 계층적 태스크 분해 에이전트.

claw-code 참고:
- query.ts의 tool_use 루프: LLM이 도구 호출 필요 여부를 판단하는 반복 루프
- 여기서는 LLM이 "이 태스크가 tool call로 직접 가능한가?"를 판단하는 재귀 분해

역할:
1. 유저 질문을 3~5개 하위 태스크로 분해
2. 각 태스크가 Tool Call 가능할 때까지 재귀 분해
3. 분해 깊이로 난이도(difficulty) 산출
4. 난이도 or 피드백 많은 영역 → chaeshin_retrieve
5. 분해 트리 + 검색된 케이스 → Executor에 전달
"""

from __future__ import annotations

import structlog
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional

from chaeshin.agents.base import BaseAgent, AgentContext
from chaeshin.schema import ProblemFeatures, ToolDef
from chaeshin.planner import GraphPlanner, TaskTree
from chaeshin.case_store import CaseStore

logger = structlog.get_logger(__name__)


class DecomposerAgent(BaseAgent):
    """계층적 태스크 분해 에이전트.

    Orchestrator가 spawn하면:
    1. 질문을 TaskTree로 분해 (GraphPlanner.create_tree)
    2. 난이도 계산
    3. Chaeshin에서 유사 케이스 검색 (난이도 높으면)
    4. 검색된 케이스를 트리에 병합
    5. 완성된 TaskTree를 결과로 반환
    """

    def __init__(
        self,
        llm_fn: Callable[[List[Dict[str, str]]], Coroutine[Any, Any, str]],
        tools: Dict[str, ToolDef],
        case_store: Optional[CaseStore] = None,
        max_depth: int = 4,
        context: Optional[AgentContext] = None,
    ):
        super().__init__(
            agent_type="decomposer",
            llm_fn=llm_fn,
            context=context,
        )
        self.planner = GraphPlanner(llm_fn=llm_fn, tools=tools)
        self.tools = tools
        self.case_store = case_store
        self.max_depth = max_depth

    async def run(
        self,
        prompt: str,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """질문을 계층적 태스크 트리로 분해.

        Args:
            prompt: 유저 질문

        Yields:
            - {"type": "progress", "message": "분해 시작..."}
            - {"type": "progress", "message": "난이도 산출: N"}
            - {"type": "progress", "message": "유사 케이스 검색 중..."}
            - {"type": "result", "output": {"task_tree": TaskTree, ...}}
        """
        yield {"type": "progress", "message": f"질문 분해 시작: {prompt[:50]}..."}

        problem = ProblemFeatures(
            request=prompt,
            category=kwargs.get("category", ""),
            keywords=kwargs.get("keywords", []),
        )

        # 1단계: 계층적 분해
        yield {"type": "progress", "message": "계층적 태스크 분해 중..."}
        task_tree = await self.planner.create_tree(
            problem, max_depth=self.max_depth,
        )

        # 2단계: 난이도 산출
        difficulty = task_tree.difficulty
        yield {"type": "progress", "message": f"난이도 산출: {difficulty} (분해 깊이)"}

        # 3단계: Chaeshin 조회 판단
        matched_cases = []
        should_use_chaeshin = self._should_retrieve(difficulty, prompt)

        if should_use_chaeshin and self.case_store:
            yield {"type": "progress", "message": "유사 케이스 검색 중..."}
            results = self.case_store.retrieve(problem, top_k=3)
            for case, score in results:
                if score >= 0.4:
                    matched_cases.append({
                        "case_id": case.metadata.case_id,
                        "similarity": score,
                        "request": case.problem_features.request,
                        "layer": self.case_store.derive_layer(case.metadata.case_id),
                        "difficulty": getattr(case.metadata, "difficulty", 0),
                    })

            if matched_cases:
                yield {
                    "type": "progress",
                    "message": f"유사 케이스 {len(matched_cases)}건 발견",
                }

        # 최종 결과
        yield {
            "type": "result",
            "output": {
                "task_tree": task_tree,
                "difficulty": difficulty,
                "matched_cases": matched_cases,
                "should_use_chaeshin": should_use_chaeshin,
                "total_leaves": len(task_tree.leaf_nodes()),
                "layers": task_tree.to_dict(),
            },
        }

    def _should_retrieve(self, difficulty: int, query: str) -> bool:
        """Chaeshin 조회 트리거 판단.

        두 축:
        - difficulty >= 2: 분해가 2단계 이상 필요한 복잡한 질문
        - 해당 영역에 feedback_count >= 3인 케이스가 있는지 (case_store 검사)
        """
        if difficulty >= 2:
            return True

        if self.case_store:
            problem = ProblemFeatures(request=query, category="", keywords=[])
            results = self.case_store.retrieve(problem, top_k=3)
            for case, score in results:
                if score >= 0.5:
                    fb = getattr(case.metadata, "feedback_count", 0)
                    if fb >= 3:
                        return True

        return False
