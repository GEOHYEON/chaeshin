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
        """임베딩 기반 유사도 검색.

        v2: feedback_count 가중치 반영.
        final_score = similarity * 0.7 + feedback_weight * 0.3
        """
        query_text = f"{problem.request} {' '.join(problem.keywords)}"
        query_vec = self.embed_fn(query_text)

        scored = []
        for case in self.cases:
            case_id = case.metadata.case_id
            if case_id not in self._embeddings:
                continue

            sim = self._cosine_similarity(query_vec, self._embeddings[case_id])

            # v2: 피드백 가중치 — 피드백 많은 케이스 우선
            fb_count = getattr(case.metadata, "feedback_count", 0)
            feedback_weight = min(fb_count / 10.0, 1.0) if fb_count > 0 else 0.0
            final_score = sim * 0.7 + feedback_weight * 0.3

            scored.append((case, round(final_score, 3)))

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
        """케이스를 저장소에 추가.

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
            try:
                text = (
                    f"{case.problem_features.request} "
                    f"{' '.join(case.problem_features.keywords)}"
                )
                self._embeddings[case.metadata.case_id] = self.embed_fn(text)
            except Exception as e:
                logger.warning(
                    "embedding_failed",
                    case_id=case.metadata.case_id,
                    error=str(e),
                )

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

    def retain_failure(
        self,
        case: Case,
        error_reason: str = "",
    ) -> str:
        """실패 케이스를 저장소에 추가.

        나중에 retrieve 시 안티패턴 경고로 활용.
        같은 상황에서 성공하면 promote_failure()로 교체 가능.

        Args:
            case: 실패한 케이스
            error_reason: 실패 사유 (예: "API rate limit 초과")

        Returns:
            저장된 case_id
        """
        case.outcome.success = False
        case.outcome.error_reason = error_reason
        return self.retain(case)

    def retrieve_with_warnings(
        self,
        problem: ProblemFeatures,
        top_k: int = 3,
        top_k_failures: int = 3,
        warning_threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """성공 케이스 + 실패 케이스를 각각 N건씩 반환.

        Args:
            problem: 현재 문제 정의
            top_k: 성공 케이스 상위 K개
            top_k_failures: 실패 케이스 상위 K개
            warning_threshold: 이 유사도 이상인 실패 케이스만 반환

        Returns:
            {"cases": [(Case, score), ...], "warnings": [(Case, score), ...]}
        """
        if not self.cases:
            return {"cases": [], "warnings": []}

        # 전체 케이스에 대해 유사도 계산
        if self.embed_fn:
            all_results = self._retrieve_by_embedding(problem, len(self.cases))
        else:
            all_results = self._retrieve_by_keywords(problem, len(self.cases))

        successes = [(c, s) for c, s in all_results if c.outcome.success]
        failures = [
            (c, s) for c, s in all_results
            if not c.outcome.success and s >= warning_threshold
        ]

        return {
            "cases": successes[:top_k],
            "warnings": failures[:top_k_failures],
        }

    def promote_failure(
        self,
        failure_case_id: str,
        successful_case: Case,
    ) -> Optional[str]:
        """실패 케이스를 성공 케이스로 교체.

        같은 상황에서 나중에 성공하면, 실패 기록을 제거하고
        성공 케이스로 대체.

        Args:
            failure_case_id: 교체할 실패 케이스 ID
            successful_case: 새 성공 케이스

        Returns:
            새 case_id (교체 성공 시), None (실패 케이스를 못 찾으면)
        """
        # 실패 케이스 찾기
        failure_idx = None
        for i, c in enumerate(self.cases):
            if c.metadata.case_id == failure_case_id and not c.outcome.success:
                failure_idx = i
                break

        if failure_idx is None:
            logger.warning("failure_not_found", case_id=failure_case_id)
            return None

        # 실패 케이스 제거
        removed = self.cases.pop(failure_idx)
        if failure_case_id in self._embeddings:
            del self._embeddings[failure_case_id]

        logger.info(
            "failure_promoted",
            old_case_id=failure_case_id,
            new_case_id=successful_case.metadata.case_id,
        )

        # 성공 케이스 저장
        return self.retain(successful_case)

    # ── v2: Hierarchy (계층 연쇄 로드) ──────────────────────────────────

    def get_case_by_id(self, case_id: str) -> Optional[Case]:
        """case_id로 케이스 조회."""
        for case in self.cases:
            if case.metadata.case_id == case_id:
                return case
        return None

    def get_children(self, case_id: str) -> List[Case]:
        """하위 레이어 케이스들 반환."""
        parent = self.get_case_by_id(case_id)
        if not parent:
            return []
        child_ids = getattr(parent.metadata, "child_case_ids", [])
        children = []
        for cid in child_ids:
            child = self.get_case_by_id(cid)
            if child:
                children.append(child)
        return children

    def get_children_recursive(self, case_id: str) -> List[Case]:
        """하위 레이어 케이스를 재귀적으로 전부 반환 (BFS)."""
        result = []
        queue = list(getattr(self.get_case_by_id(case_id), "metadata", CaseMetadata()).child_case_ids or [])
        visited = set()
        while queue:
            cid = queue.pop(0)
            if cid in visited:
                continue
            visited.add(cid)
            child = self.get_case_by_id(cid)
            if child:
                result.append(child)
                queue.extend(getattr(child.metadata, "child_case_ids", []))
        return result

    def get_parent(self, case_id: str) -> Optional[Case]:
        """상위 레이어 케이스 반환."""
        case = self.get_case_by_id(case_id)
        if not case:
            return None
        parent_id = getattr(case.metadata, "parent_case_id", "")
        if not parent_id:
            return None
        return self.get_case_by_id(parent_id)

    def get_ancestry(self, case_id: str) -> List[Case]:
        """루트까지의 조상 케이스 체인 반환 (자신 제외, 부모→조부모 순)."""
        result = []
        current = self.get_case_by_id(case_id)
        visited = set()
        while current:
            parent_id = getattr(current.metadata, "parent_case_id", "")
            if not parent_id or parent_id in visited:
                break
            visited.add(parent_id)
            parent = self.get_case_by_id(parent_id)
            if parent:
                result.append(parent)
                current = parent
            else:
                break
        return result

    # ── v2: Feedback (피드백 반영) ────────────────────────────────────

    def add_feedback(
        self,
        case_id: str,
        feedback: str,
        feedback_type: str = "modify",
    ) -> Optional[Case]:
        """케이스에 피드백을 기록.

        Args:
            case_id: 대상 케이스 ID
            feedback: 피드백 내용 (자연어)
            feedback_type: escalate / modify / simplify / correct / reject

        Returns:
            업데이트된 Case (없으면 None)
        """
        case = self.get_case_by_id(case_id)
        if not case:
            logger.warning("feedback_case_not_found", case_id=case_id)
            return None

        case.metadata.feedback_count = getattr(case.metadata, "feedback_count", 0) + 1
        fb_log = getattr(case.metadata, "feedback_log", [])
        fb_log.append(f"[{feedback_type}] {feedback}")
        case.metadata.feedback_log = fb_log
        case.metadata.updated_at = datetime.now().isoformat()

        logger.info(
            "feedback_added",
            case_id=case_id,
            feedback_type=feedback_type,
            feedback_count=case.metadata.feedback_count,
        )
        return case

    def link_parent_child(self, parent_case_id: str, child_case_id: str, parent_node_id: str = ""):
        """부모-자식 관계 설정.

        parent의 child_case_ids에 child를 추가하고,
        child의 parent_case_id/parent_node_id를 설정.
        """
        parent = self.get_case_by_id(parent_case_id)
        child = self.get_case_by_id(child_case_id)
        if not parent or not child:
            logger.warning("link_failed", parent=parent_case_id, child=child_case_id)
            return

        child_ids = getattr(parent.metadata, "child_case_ids", [])
        if child_case_id not in child_ids:
            child_ids.append(child_case_id)
            parent.metadata.child_case_ids = child_ids

        child.metadata.parent_case_id = parent_case_id
        if parent_node_id:
            child.metadata.parent_node_id = parent_node_id

        logger.info("linked", parent=parent_case_id, child=child_case_id, node=parent_node_id)

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
