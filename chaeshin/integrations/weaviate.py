"""
Weaviate Case Store — Weaviate 기반 CBR 케이스 저장소.

bt_agent_monitoring의 Experience 컬렉션과 호환되는 스키마를 사용합니다.
experienceType: "chaeshin-cbr"로 필터링하여 Chaeshin 전용 케이스를 관리합니다.

사용법:
    from chaeshin.integrations.weaviate import WeaviateCaseStore

    store = WeaviateCaseStore(
        weaviate_url="http://localhost:8080",
        embed_fn=adapter.embed_fn,
    )
"""

from __future__ import annotations

import json
import structlog
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import weaviate
    from weaviate.classes.query import Filter
except ImportError as e:
    raise ImportError(
        "weaviate-client 패키지가 필요합니다: pip install 'chaeshin[weaviate]'"
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

COLLECTION_NAME = "Experience"
EXPERIENCE_TYPE = "chaeshin-cbr"


class WeaviateCaseStore:
    """Weaviate 기반 CBR 케이스 저장소.

    bt_agent_monitoring의 Experience 컬렉션과 동일한 스키마를 사용하여
    모니터링 UI에서 직접 조회·수정·삭제가 가능합니다.

    스키마 매핑:
        experienceType = "chaeshin-cbr"
        userQuery      = problem_features.request
        isSuccessful   = outcome.success
        keywords       = problem_features.keywords
        inputJson      = problem_features (JSON)
        outputJson     = solution.tool_graph (JSON)
        metadataJson   = {outcome, metadata} (JSON)
    """

    def __init__(
        self,
        weaviate_url: str = "http://localhost:8080",
        grpc_port: int = 50051,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        similarity_threshold: float = 0.7,
    ):
        self.embed_fn = embed_fn
        self.similarity_threshold = similarity_threshold
        self.cases: List[Case] = []

        # Weaviate 연결
        from urllib.parse import urlparse
        parsed = urlparse(weaviate_url)
        self._client = weaviate.connect_to_local(
            host=parsed.hostname or "localhost",
            port=int(parsed.port or 8080),
            grpc_port=grpc_port,
        )

        # 컬렉션 확보
        self._ensure_collection()

        # 기존 케이스 로드
        self._load_existing()

        logger.info(
            "weaviate_store_initialized",
            url=weaviate_url,
            case_count=len(self.cases),
        )

    def _ensure_collection(self):
        """Experience 컬렉션이 없으면 생성."""
        if self._client.collections.exists(COLLECTION_NAME):
            return
        self._client.collections.create(
            name=COLLECTION_NAME,
            vectorizer_config=weaviate.classes.config.Configure.Vectorizer.none(),
            properties=[
                weaviate.classes.config.Property(name="experienceType", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="chatbotId", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="userQuery", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="isSuccessful", data_type=weaviate.classes.config.DataType.BOOL),
                weaviate.classes.config.Property(name="feedback", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="keywords", data_type=weaviate.classes.config.DataType.TEXT_ARRAY),
                weaviate.classes.config.Property(name="inputJson", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="outputJson", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="metadataJson", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="postgresId", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="sourceLogId", data_type=weaviate.classes.config.DataType.TEXT),
                weaviate.classes.config.Property(name="createdAt", data_type=weaviate.classes.config.DataType.DATE),
            ],
        )
        logger.info("weaviate_collection_created", name=COLLECTION_NAME)

    def _load_existing(self):
        """Weaviate에서 기존 chaeshin-cbr 케이스를 메모리 캐시로 로드."""
        coll = self._client.collections.get(COLLECTION_NAME)
        try:
            result = coll.query.fetch_objects(
                filters=Filter.by_property("experienceType").equal(EXPERIENCE_TYPE),
                limit=1000,
            )
            for obj in result.objects:
                case = self._weaviate_to_case(obj.properties, str(obj.uuid))
                if case:
                    self.cases.append(case)
        except Exception as e:
            logger.warning("weaviate_load_failed", error=str(e))

    # ── Retrieve ──────────────────────────────────────────────────────

    def retrieve(
        self,
        problem: ProblemFeatures,
        top_k: int = 3,
    ) -> List[Tuple[Case, float]]:
        """유사한 케이스를 Weaviate에서 검색."""
        if not self.cases:
            return []

        query_text = self._problem_to_text(problem)

        coll = self._client.collections.get(COLLECTION_NAME)

        if self.embed_fn:
            query_vec = self.embed_fn(query_text)
            result = coll.query.near_vector(
                near_vector=query_vec,
                filters=Filter.by_property("experienceType").equal(EXPERIENCE_TYPE),
                limit=min(top_k, len(self.cases)),
                return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
            )
        else:
            result = coll.query.near_text(
                query=query_text,
                filters=Filter.by_property("experienceType").equal(EXPERIENCE_TYPE),
                limit=min(top_k, len(self.cases)),
                return_metadata=weaviate.classes.query.MetadataQuery(distance=True),
            )

        scored: List[Tuple[Case, float]] = []
        for obj in result.objects:
            distance = obj.metadata.distance if obj.metadata and obj.metadata.distance else 0
            similarity = round(1.0 - distance, 3)
            case = self._find_case_by_id(str(obj.uuid))
            if case:
                scored.append((case, similarity))

        return scored

    def retrieve_best(self, problem: ProblemFeatures) -> Optional[Case]:
        results = self.retrieve(problem, top_k=1)
        if results and results[0][1] >= self.similarity_threshold:
            return results[0][0]
        return None

    def retrieve_with_warnings(
        self,
        problem: ProblemFeatures,
        top_k: int = 3,
        warning_threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """성공 케이스 + 안티패턴 경고."""
        all_results = self.retrieve(problem, top_k=len(self.cases) or 10)
        successes = [(c, s) for c, s in all_results if c.outcome.success]
        failures = [
            (c, s) for c, s in all_results
            if not c.outcome.success and s >= warning_threshold
        ]
        return {
            "cases": successes[:top_k],
            "warnings": failures[:3],
        }

    # ── Retain ────────────────────────────────────────────────────────

    def retain(self, case: Case) -> str:
        """케이스를 Weaviate + 메모리에 저장."""
        case_id = case.metadata.case_id
        case.metadata.updated_at = datetime.now().isoformat()

        props = self._case_to_weaviate(case)
        coll = self._client.collections.get(COLLECTION_NAME)

        upsert_kwargs: Dict[str, Any] = {"properties": props}
        if self.embed_fn:
            text = self._problem_to_text(case.problem_features)
            upsert_kwargs["vector"] = self.embed_fn(text)

        # Weaviate는 UUID 기반이므로 case_id를 UUID로 사용
        try:
            from uuid import UUID
            uuid_obj = UUID(case_id)
        except ValueError:
            import uuid as uuid_mod
            uuid_obj = uuid_mod.uuid5(uuid_mod.NAMESPACE_DNS, case_id)

        # 기존 객체 삭제 후 삽입 (upsert 대용)
        try:
            coll.data.delete_by_id(uuid_obj)
        except Exception:
            pass

        coll.data.insert(
            properties=props,
            uuid=uuid_obj,
            vector=upsert_kwargs.get("vector"),
        )

        # 메모리 캐시 업데이트
        existing_idx = None
        for i, c in enumerate(self.cases):
            if c.metadata.case_id == case_id:
                existing_idx = i
                break

        if existing_idx is not None:
            self.cases[existing_idx] = case
        else:
            self.cases.append(case)

        logger.info("case_retained_weaviate", case_id=case_id)
        return case_id

    def retain_if_successful(self, case: Case, min_satisfaction: float = 0.7) -> Optional[str]:
        if case.outcome.success and case.outcome.user_satisfaction >= min_satisfaction:
            return self.retain(case)
        return None

    def retain_failure(self, case: Case, error_reason: str = "") -> str:
        case.outcome.success = False
        case.outcome.error_reason = error_reason
        return self.retain(case)

    def promote_failure(self, failure_case_id: str, successful_case: Case) -> Optional[str]:
        failure_idx = None
        for i, c in enumerate(self.cases):
            if c.metadata.case_id == failure_case_id and not c.outcome.success:
                failure_idx = i
                break

        if failure_idx is None:
            return None

        # 실패 케이스 제거
        self.cases.pop(failure_idx)
        coll = self._client.collections.get(COLLECTION_NAME)
        try:
            from uuid import UUID
            coll.data.delete_by_id(UUID(failure_case_id))
        except Exception:
            pass

        return self.retain(successful_case)

    # ── Record Usage ──────────────────────────────────────────────────

    def record_usage(self, case_id: str, satisfaction: float):
        for case in self.cases:
            if case.metadata.case_id == case_id:
                meta = case.metadata
                total = meta.avg_satisfaction * meta.used_count + satisfaction
                meta.used_count += 1
                meta.avg_satisfaction = round(total / meta.used_count, 3)
                meta.updated_at = datetime.now().isoformat()
                self.retain(case)
                return

    # ── Serialization ─────────────────────────────────────────────────

    def load_json(self, data: str):
        """JSON에서 케이스를 로드하고 Weaviate에 저장."""
        raw_list = json.loads(data)
        for raw in raw_list:
            case = self._dict_to_case(raw)
            self.retain(case)

    def to_json(self) -> str:
        return json.dumps(
            [asdict(c) for c in self.cases],
            ensure_ascii=False,
            indent=2,
        )

    # ── Info ──────────────────────────────────────────────────────────

    def count(self) -> int:
        return len(self.cases)

    def stats(self) -> Dict[str, Any]:
        return {
            "total_cases": len(self.cases),
            "categories": list({c.problem_features.category for c in self.cases}),
            "avg_satisfaction": (
                round(sum(c.outcome.user_satisfaction for c in self.cases) / len(self.cases), 3)
                if self.cases else 0
            ),
        }

    def close(self):
        """Weaviate 연결 종료."""
        self._client.close()

    # ── Helpers ────────────────────────────────────────────────────────

    def _find_case_by_id(self, case_id: str) -> Optional[Case]:
        for c in self.cases:
            if c.metadata.case_id == case_id:
                return c
        return None

    @staticmethod
    def _problem_to_text(problem: ProblemFeatures) -> str:
        parts = [problem.request]
        if problem.category:
            parts.append(f"카테고리: {problem.category}")
        if problem.keywords:
            parts.append(" ".join(problem.keywords))
        return " | ".join(parts)

    @staticmethod
    def _case_to_weaviate(case: Case) -> Dict[str, Any]:
        """Case → Weaviate Experience 프로퍼티."""
        return {
            "experienceType": EXPERIENCE_TYPE,
            "chatbotId": "",
            "userQuery": case.problem_features.request,
            "isSuccessful": case.outcome.success,
            "feedback": case.outcome.error_reason or "",
            "keywords": case.problem_features.keywords,
            "inputJson": json.dumps(asdict(case.problem_features), ensure_ascii=False),
            "outputJson": json.dumps(asdict(case.solution.tool_graph), ensure_ascii=False),
            "metadataJson": json.dumps({
                "outcome": asdict(case.outcome),
                "metadata": asdict(case.metadata),
            }, ensure_ascii=False),
            "postgresId": "",
            "sourceLogId": case.metadata.case_id,
            "createdAt": case.metadata.created_at,
        }

    @staticmethod
    def _weaviate_to_case(props: Dict[str, Any], uuid: str) -> Optional[Case]:
        """Weaviate Experience 프로퍼티 → Case."""
        try:
            pf_data = json.loads(props.get("inputJson", "{}"))
            tg_data = json.loads(props.get("outputJson", "{}"))
            meta_data = json.loads(props.get("metadataJson", "{}"))

            pf = ProblemFeatures(**pf_data)
            tg = ToolGraph(
                nodes=[GraphNode(**n) for n in tg_data.get("nodes", [])],
                edges=[GraphEdge(**e) for e in tg_data.get("edges", [])],
                parallel_groups=tg_data.get("parallel_groups", []),
                entry_nodes=tg_data.get("entry_nodes", []),
                max_loops=tg_data.get("max_loops", 3),
            )
            sol = Solution(tool_graph=tg)

            outcome_data = meta_data.get("outcome", {})
            metadata_obj = meta_data.get("metadata", {})

            out = Outcome(**outcome_data)
            meta = CaseMetadata(**metadata_obj)

            return Case(problem_features=pf, solution=sol, outcome=out, metadata=meta)
        except Exception as e:
            logger.warning("weaviate_to_case_failed", error=str(e), uuid=uuid)
            return None

    @staticmethod
    def _dict_to_case(d: Dict[str, Any]) -> Case:
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
        return Case(problem_features=pf, solution=sol, outcome=out, metadata=meta)
