"""
ChromaDB Case Store — 벡터 DB 기반 CBR 케이스 저장소.

ChromaDB를 사용해 케이스를 임베딩으로 저장하고, 유사도 검색을 수행합니다.
in-memory 또는 영구 저장 모두 지원합니다.

사용법:
    from chaeshin.integrations.chroma import ChromaCaseStore
    from chaeshin.integrations.openai import OpenAIAdapter

    adapter = OpenAIAdapter()
    store = ChromaCaseStore(
        embed_fn=adapter.embed_fn,
        persist_dir="./data/chroma",
    )
"""

from __future__ import annotations

import json
import structlog
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import chromadb
    from chromadb.config import Settings
except ImportError as e:
    raise ImportError(
        "chromadb 패키지가 필요합니다: pip install 'chaeshin[llm]'"
    ) from e

from chaeshin.schema import (
    Case,
    ProblemFeatures,
    Solution,
    Outcome,
    CaseMetadata,
    ToolGraph,
    GraphNode,
    GraphEdge,
)

logger = structlog.get_logger(__name__)


class ChromaCaseStore:
    """ChromaDB 기반 CBR 케이스 저장소.

    in-memory CaseStore와 동일한 인터페이스를 제공하되,
    ChromaDB를 통해 영구 저장 + 벡터 검색을 지원합니다.
    """

    def __init__(
        self,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        collection_name: str = "chaeshin_cases",
        persist_dir: Optional[str] = None,
        similarity_threshold: float = 0.7,
    ):
        """
        Args:
            embed_fn: 텍스트 → 임베딩 벡터 변환 함수
            collection_name: ChromaDB 컬렉션 이름
            persist_dir: 영구 저장 경로 (None이면 in-memory)
            similarity_threshold: 유사도 임계값
        """
        self.embed_fn = embed_fn
        self.similarity_threshold = similarity_threshold
        self.cases: List[Case] = []  # 메모리 캐시

        # ChromaDB 클라이언트 초기화
        if persist_dir:
            self._client = chromadb.PersistentClient(path=persist_dir)
            logger.info("chroma_persistent", path=persist_dir)
        else:
            self._client = chromadb.EphemeralClient()
            logger.info("chroma_ephemeral")

        # 컬렉션 생성/로드
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            "chroma_store_initialized",
            collection=collection_name,
            existing_count=self._collection.count(),
        )

    # ── Retrieve ──────────────────────────────────────────────────────

    def retrieve(
        self,
        problem: ProblemFeatures,
        top_k: int = 3,
    ) -> List[Tuple[Case, float]]:
        """유사한 케이스를 ChromaDB에서 검색.

        Args:
            problem: 현재 문제 정의
            top_k: 상위 K개 반환

        Returns:
            (Case, similarity_score) 튜플 리스트
        """
        if self._collection.count() == 0:
            return []

        query_text = self._problem_to_text(problem)

        if self.embed_fn:
            query_embedding = self.embed_fn(query_text)
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )
        else:
            # 임베딩 없으면 텍스트 검색 fallback
            results = self._collection.query(
                query_texts=[query_text],
                n_results=min(top_k, self._collection.count()),
                include=["documents", "metadatas", "distances"],
            )

        scored: List[Tuple[Case, float]] = []
        if results and results["ids"] and results["ids"][0]:
            for i, case_id in enumerate(results["ids"][0]):
                # ChromaDB cosine distance → similarity (1 - distance)
                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = round(1.0 - distance, 3)

                # 메모리 캐시에서 Case 객체 찾기
                case = self._find_case_by_id(case_id)
                if case:
                    scored.append((case, similarity))

        return scored

    def retrieve_best(self, problem: ProblemFeatures) -> Optional[Case]:
        """가장 유사한 케이스 1개만 반환."""
        results = self.retrieve(problem, top_k=1)
        if results and results[0][1] >= self.similarity_threshold:
            return results[0][0]
        return None

    # ── Retain ────────────────────────────────────────────────────────

    def retain(self, case: Case) -> str:
        """케이스를 ChromaDB + 메모리에 저장.

        Returns:
            저장된 case_id
        """
        case_id = case.metadata.case_id
        case.metadata.updated_at = datetime.now().isoformat()

        # 임베딩 텍스트
        text = self._problem_to_text(case.problem_features)

        # Case를 JSON으로 직렬화해서 metadata에 저장
        case_json = json.dumps(asdict(case), ensure_ascii=False)

        # ChromaDB upsert
        upsert_kwargs = {
            "ids": [case_id],
            "documents": [text],
            "metadatas": [{"case_json": case_json[:40000]}],  # ChromaDB metadata 크기 제한
        }

        if self.embed_fn:
            embedding = self.embed_fn(text)
            upsert_kwargs["embeddings"] = [embedding]

        self._collection.upsert(**upsert_kwargs)

        # 메모리 캐시 업데이트
        existing_idx = None
        for i, c in enumerate(self.cases):
            if c.metadata.case_id == case_id:
                existing_idx = i
                break

        if existing_idx is not None:
            self.cases[existing_idx] = case
            logger.info("case_updated", case_id=case_id)
        else:
            self.cases.append(case)
            logger.info("case_retained", case_id=case_id)

        return case_id

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
                total = meta.avg_satisfaction * meta.used_count + satisfaction
                meta.used_count += 1
                meta.avg_satisfaction = round(total / meta.used_count, 3)
                meta.updated_at = datetime.now().isoformat()
                # ChromaDB에도 반영
                self.retain(case)
                return

    # ── Serialization ─────────────────────────────────────────────────

    def load_json(self, data: str):
        """JSON에서 케이스를 로드하고 ChromaDB에 저장."""
        raw_list = json.loads(data)

        texts = []
        ids = []
        metadatas = []
        cases = []

        for raw in raw_list:
            case = self._dict_to_case(raw)
            cases.append(case)

            case_id = case.metadata.case_id
            text = self._problem_to_text(case.problem_features)
            case_json = json.dumps(raw, ensure_ascii=False)

            texts.append(text)
            ids.append(case_id)
            metadatas.append({"case_json": case_json[:40000]})

        # 임베딩 배치 생성
        embeddings = None
        if self.embed_fn:
            embeddings = [self.embed_fn(t) for t in texts]

        # ChromaDB에 일괄 저장
        upsert_kwargs = {
            "ids": ids,
            "documents": texts,
            "metadatas": metadatas,
        }
        if embeddings:
            upsert_kwargs["embeddings"] = embeddings

        self._collection.upsert(**upsert_kwargs)

        # 메모리 캐시
        self.cases.extend(cases)

        logger.info(
            "cases_loaded",
            count=len(cases),
            chroma_total=self._collection.count(),
        )

    def to_json(self) -> str:
        """전체 케이스를 JSON으로 직렬화."""
        return json.dumps(
            [asdict(c) for c in self.cases],
            ensure_ascii=False,
            indent=2,
        )

    # ── Info ──────────────────────────────────────────────────────────

    def count(self) -> int:
        """저장된 케이스 수."""
        return self._collection.count()

    def stats(self) -> Dict[str, Any]:
        """저장소 통계."""
        return {
            "total_cases": self._collection.count(),
            "memory_cases": len(self.cases),
            "categories": list({c.problem_features.category for c in self.cases}),
            "avg_satisfaction": (
                round(
                    sum(c.outcome.user_satisfaction for c in self.cases)
                    / len(self.cases),
                    3,
                )
                if self.cases
                else 0
            ),
        }

    # ── Helpers ────────────────────────────────────────────────────────

    def _find_case_by_id(self, case_id: str) -> Optional[Case]:
        for c in self.cases:
            if c.metadata.case_id == case_id:
                return c
        return None

    @staticmethod
    def _problem_to_text(problem: ProblemFeatures) -> str:
        """ProblemFeatures → 검색용 텍스트."""
        parts = [problem.request]
        if problem.category:
            parts.append(f"카테고리: {problem.category}")
        if problem.keywords:
            parts.append(" ".join(problem.keywords))
        if problem.constraints:
            parts.append(" ".join(problem.constraints))
        return " | ".join(parts)

    @staticmethod
    def _dict_to_case(d: Dict[str, Any]) -> Case:
        """딕셔너리 → Case 변환."""
        pf = ProblemFeatures(**d["problem_features"])

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
