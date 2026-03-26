"""
Case Store — CBR 케이스 저장/검색/적응.

Retrieve → Reuse → Revise → Retain (CBR 4R 사이클)

요리로 비유하면:
- Retrieve: "김치찌개" 요청이 들어오면, 이전에 성공한 김치찌개 레시피를 찾아옴
- Reuse: 찾은 레시피를 이번 상황에 맞게 적용
- Revise: 실행 중 문제가 생기면 레시피를 수정
- Retain: 성공하면 수정된 레시피를 다시 저장
"""

from __future__ import annotations

import json
import structlog
from datetime import datetime
from dataclasses import asdict
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from chaeshin.schema import (
    Case,
    ProblemFeatures,
    Solution,
    Outcome,
    CaseMetadata,
    ToolGraph,
)

logger = structlog.get_logger(__name__)


class CaseStore:
    """CBR 케이스 저장소.

    기본 구현은 in-memory.
    프로덕션에서는 VectorDB (Weaviate, Pinecone 등)로 교체.
    """

    def __init__(
        self,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        similarity_threshold: float = 0.7,
    ):
        """
        Args:
            embed_fn: 텍스트 → 임베딩 벡터 변환 함수 (None이면 키워드 매칭)
            similarity_threshold: 유사도 임계값
        """
        self.cases: List[Case] = []
        self.embed_fn = embed_fn
        self.similarity_threshold = similarity_threshold
        self._embeddings: Dict[str, List[float]] = {}  # case_id → embedding

    # ── Retrieve ──────────────────────────────────────────────────────

    def retrieve(
        self,
        problem: ProblemFeatures,
        top_k: int = 3,
    ) -> List[Tuple[Case, float]]:
        """유사한 케이스를 검색.

        Args:
            problem: 현재 문제 정의
            top_k: 상위 K개 반환

        Returns:
            (Case, similarity_score) 튜플 리스트, 점수 내림차순
        """
        if not self.cases:
            return []

        if self.embed_fn:
            return self._retrieve_by_embedding(problem, top_k)
        else:
            return self._retrieve_by_keywords(problem, top_k)

    def retrieve_best(self, problem: ProblemFeatures) -> Optional[Case]:
        """가장 유사한 케이스 1개만 반환."""
        results = self.retrieve(problem, top_k=1)
        if results and results[0][1] >= self.similarity_threshold:
            return results[0][0]
        return None

    def _retrieve_by_keywords(
        self,
        problem: ProblemFeatures,
        top_k: int,
    ) -> List[Tuple[Case, float]]:
        """키워드 기반 유사도 검색 (임베딩 없을 때 fallback)."""
        query_keywords = set(problem.keywords)
        query_category = problem.category

        scored = []
        for case in self.cases:
            score = 0.0
            case_keywords = set(case.problem_features.keywords)

            # 카테고리 일치 가중치
            if case.problem_features.category == query_category:
                score += 0.4

            # 키워드 Jaccard 유사도
            if query_keywords and case_keywords:
                intersection = query_keywords & case_keywords
                union = query_keywords | case_keywords
                jaccard = len(intersection) / len(union) if union else 0
                score += jaccard * 0.4

            # 성공률/만족도 가중치
            if case.outcome.success:
                score += 0.1
            score += case.outcome.user_satisfaction * 0.1

            scored.append((case, round(score, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _retrieve_by_embedding(
        self,
        problem: ProblemFeatures,
        top_k: int,
    ) -> List[Tuple[Case, float]]:
        """임베딩 기반 유사도 검색."""
        query_text = f"{problem.request} {' '.join(problem.keywords)}"
        query_vec = self.embed_fn(query_text)

        scored = []
        for case in self.cases:
            case_id = case.metadata.case_id
            if case_id not in self._embeddings:
                continue

            sim = self._cosine_similarity(query_vec, self._embeddings[case_id])
            scored.append((case, round(sim, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x ** 2 for x in a) ** 0.5
        norm_b = sum(x ** 2 for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ── Retain ────────────────────────────────────────────────────────

    def retain(self, case: Case) -> str:
        """성공한 케이스를 저장소에 추가.

        동일 case_id가 있으면 업데이트.

        Returns:
            저장된 case_id
        """
        existing_idx = None
        for i, c in enumerate(self.cases):
            if c.metadata.case_id == case.metadata.case_id:
                existing_idx = i
                break

        case.metadata.updated_at = datetime.now().isoformat()

        if existing_idx is not None:
            self.cases[existing_idx] = case
            logger.info("case_updated", case_id=case.metadata.case_id)
        else:
            self.cases.append(case)
            logger.info("case_retained", case_id=case.metadata.case_id)

        # 임베딩 생성 (embed_fn이 있을 때)
        if self.embed_fn:
            text = (
                f"{case.problem_features.request} "
                f"{' '.join(case.problem_features.keywords)}"
            )
            self._embeddings[case.metadata.case_id] = self.embed_fn(text)

        return case.metadata.case_id

    def retain_if_successful(
        self,
        case: Case,
        min_satisfaction: float = 0.7,
    ) -> Optional[str]:
        """성공하고 만족도가 기준 이상인 경우에만 저장."""
        if case.outcome.success and case.outcome.user_satisfaction >= min_satisfaction:
            return self.retain(case)
        logger.info(
            "case_not_retained",
            case_id=case.metadata.case_id,
            success=case.outcome.success,
            satisfaction=case.outcome.user_satisfaction,
        )
        return None

    # ── Record Usage ──────────────────────────────────────────────────

    def record_usage(self, case_id: str, satisfaction: float):
        """케이스 사용 기록 업데이트."""
        for case in self.cases:
            if case.metadata.case_id == case_id:
                meta = case.metadata
                # 이동 평균
                total = meta.avg_satisfaction * meta.used_count + satisfaction
                meta.used_count += 1
                meta.avg_satisfaction = round(total / meta.used_count, 3)
                meta.updated_at = datetime.now().isoformat()
                return

    # ── Serialization ─────────────────────────────────────────────────

    def to_json(self) -> str:
        """전체 케이스를 JSON으로 직렬화."""
        return json.dumps(
            [asdict(c) for c in self.cases],
            ensure_ascii=False,
            indent=2,
        )

    def load_json(self, data: str):
        """JSON에서 케이스 로드."""
        raw_list = json.loads(data)
        for raw in raw_list:
            case = self._dict_to_case(raw)
            self.cases.append(case)
            if self.embed_fn:
                text = (
                    f"{case.problem_features.request} "
                    f"{' '.join(case.problem_features.keywords)}"
                )
                self._embeddings[case.metadata.case_id] = self.embed_fn(text)

    @staticmethod
    def _dict_to_case(d: Dict[str, Any]) -> Case:
        """딕셔너리 → Case 변환."""
        from chaeshin.schema import (
            GraphNode, GraphEdge, ToolGraph,
            ProblemFeatures, Solution, Outcome, CaseMetadata,
        )

        pf = ProblemFeatures(**{
            k: v for k, v in d["problem_features"].items()
        })

        tg_data = d["solution"]["tool_graph"]
        tg = ToolGraph(
            nodes=[GraphNode(**n) for n in tg_data.get("nodes", [])],
            edges=[GraphEdge(**e) for e in tg_data.get("edges", [])],
            parallel_groups=tg_data.get("parallel_groups", []),
            entry_nodes=tg_data.get("entry_nodes", []),
            max_loops=tg_data.get("max_loops", 3),
        )

        sol = Solution(tool_graph=tg)
        out = Outcome(**d["outcome"])
        meta = CaseMetadata(**d["metadata"])

        return Case(
            problem_features=pf,
            solution=sol,
            outcome=out,
            metadata=meta,
        )
