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
import os
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

# 기본 컬렉션. bt-monitoring 은 ExperienceType.weaviateClassName 으로 종류별
# 컬렉션(ProcChaeshinCbr 등)을 관리하므로, 그쪽과 같은 곳을 보게 하려면
# collection_name 인자나 CHAESHIN_WEAVIATE_COLLECTION env 로 지정한다.
# 기본값을 바꾸지 않는 이유: 기존 배포가 조용히 다른 컬렉션을 보게 되면
# 케이스가 통째로 사라진 것처럼 보인다.
COLLECTION_NAME = "Experience"
EXPERIENCE_TYPE = "chaeshin-cbr"

# 소속을 알 수 없는 레거시 케이스의 chatbotId. 모든 에이전트가 함께 본다.
# 빈 문자열을 쓰지 않는 이유는 _scope_filter 주석 참조.
LEGACY_SCOPE = "legacy"


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
        collection_name: Optional[str] = None,
        chatbot_id: str = "",
    ):
        """Weaviate 연결과 케이스 범위를 구성하고 기존 데이터를 로드한다.

        컬렉션은 명시적 인자, 환경변수, 기본값 순으로 선택한다. ``chatbot_id``가
        있으면 조회와 저장을 해당 챗봇 및 귀속 불명 레거시 케이스로 한정한다.
        """
        self.embed_fn = embed_fn
        self.similarity_threshold = similarity_threshold
        self.cases: List[Case] = []
        # 어느 컬렉션을 볼지. 인자 > env > 기본값.
        self.collection_name = (
            collection_name
            or os.environ.get("CHAESHIN_WEAVIATE_COLLECTION", "").strip()
            or COLLECTION_NAME
        )
        # 이 저장소를 쓰는 챗봇. 값이 있으면 retain 시 기록하고 retrieve 시 필터한다
        # — 없으면 모든 에이전트가 한 케이스 풀을 공유해 서로의 절차가 힌트로 섞인다.
        self.chatbot_id = chatbot_id or os.environ.get("GSX2_CHATBOT_ID", "").strip()

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
        if self._client.collections.exists(self.collection_name):
            return
        self._client.collections.create(
            name=self.collection_name,
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
        logger.info("weaviate_collection_created", name=self.collection_name)

    @property
    def _is_shared_collection(self) -> bool:
        """레거시 공용 컬렉션인지. 종류별 컬렉션(ProcChaeshinCbr 등)은 아니다."""
        return self.collection_name == COLLECTION_NAME

    def _scope_filter(self):
        """검색 스코프 필터. 없으면 None.

        experienceType 은 **공용 컬렉션에서만** 건다. 종류별 컬렉션은 컬렉션
        자체가 종류라 이 속성이 아예 없어서, 걸면 조건에 맞는 객체가 0건이 된다.
        """
        clauses = []
        if self._is_shared_collection:
            clauses.append(Filter.by_property("experienceType").equal(EXPERIENCE_TYPE))
        if self.chatbot_id:
            # 내 케이스 + 소속 미상 레거시(LEGACY_SCOPE).
            # 엄격히 내 것만 보면 chatbotId 를 기록하기 이전에 쌓인 케이스가 전부
            # 사라져 CBR 이 콜드 스타트한다. 레거시는 어차피 귀속이 불가능하므로
            # 당분간 공용으로 두고, 새 케이스가 충분히 쌓이면 잘라낸다.
            # 빈 문자열로 표시하지 않는 이유: Weaviate 는 equal("") 을 필터로 못 쓴다
            # ("invalid search term, only stopwords provided" 로 쿼리 자체가 실패).
            clauses.append(Filter.any_of([
                Filter.by_property("chatbotId").equal(self.chatbot_id),
                Filter.by_property("chatbotId").equal(LEGACY_SCOPE),
            ]))
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else Filter.all_of(clauses)

    def _load_existing(self):
        """Weaviate에서 기존 chaeshin-cbr 케이스를 메모리 캐시로 로드."""
        coll = self._client.collections.get(self.collection_name)
        try:
            result = coll.query.fetch_objects(
                filters=self._scope_filter(),
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

        coll = self._client.collections.get(self.collection_name)

        query_vec = self.embed_fn(query_text) if self.embed_fn else None
        result = coll.query.hybrid(
            query=query_text,
            vector=query_vec,
            alpha=0.65 if query_vec else 0.0,
            query_properties=["userQuery", "keywords", "feedback", "inputJson"],
            filters=self._scope_filter(),
            limit=min(top_k, len(self.cases)),
            return_metadata=weaviate.classes.query.MetadataQuery(distance=True, score=True),
        )

        scored: List[Tuple[Case, float]] = []
        for obj in result.objects:
            # Weaviate 버전에 따라 hybrid 결과가 distance 또는 score만 제공하므로
            # 가능한 값을 0~1 유사도로 정규화하고 둘 다 없으면 0으로 둔다.
            distance = getattr(obj.metadata, "distance", None) if obj.metadata else None
            raw_score = getattr(obj.metadata, "score", None) if obj.metadata else None
            if isinstance(distance, (int, float)):
                similarity = round(max(0.0, 1.0 - float(distance)), 3)
            else:
                try:
                    similarity = round(max(0.0, min(1.0, float(raw_score))), 3)
                except (TypeError, ValueError):
                    similarity = 0.0

            case = self._find_case_by_id(self._case_id_from_weaviate(obj.properties, str(obj.uuid)))
            if case:
                scored.append((case, similarity))

        return scored

    def retrieve_best(self, problem: ProblemFeatures) -> Optional[Case]:
        """유사도 임계값을 넘는 최상위 케이스 한 건을 반환한다."""
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
        coll = self._client.collections.get(self.collection_name)

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
            # 대상이 없거나 삭제가 실패해도 뒤의 insert로 최신 상태를 기록한다.
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
        """성공했고 만족도 기준을 넘은 케이스만 저장한다."""
        if case.outcome.success and case.outcome.user_satisfaction >= min_satisfaction:
            return self.retain(case)
        return None

    def retain_failure(self, case: Case, error_reason: str = "") -> str:
        """케이스를 실패 상태로 표시하고 안티패턴으로 저장한다."""
        case.outcome.success = False
        case.outcome.error_reason = error_reason
        return self.retain(case)

    def promote_failure(self, failure_case_id: str, successful_case: Case) -> Optional[str]:
        """기존 실패 케이스를 제거하고 교정된 성공 케이스로 대체한다.

        실패 케이스를 찾지 못하면 ``None``을 반환한다.
        """
        failure_idx = None
        for i, c in enumerate(self.cases):
            if c.metadata.case_id == failure_case_id and not c.outcome.success:
                failure_idx = i
                break

        if failure_idx is None:
            return None

        # 실패 케이스 제거
        self.cases.pop(failure_idx)
        coll = self._client.collections.get(self.collection_name)
        try:
            from uuid import UUID
            coll.data.delete_by_id(UUID(failure_case_id))
        except Exception:
            pass

        return self.retain(successful_case)

    # ── Record Usage ──────────────────────────────────────────────────

    def record_usage(self, case_id: str, satisfaction: float):
        """사용 횟수와 만족도 이동 평균을 갱신해 다시 저장한다."""
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
        """메모리 캐시의 전체 케이스를 JSON 문자열로 직렬화한다."""
        return json.dumps(
            [asdict(c) for c in self.cases],
            ensure_ascii=False,
            indent=2,
        )

    # ── Info ──────────────────────────────────────────────────────────

    def count(self) -> int:
        """현재 메모리 캐시에 로드된 케이스 수를 반환한다."""
        return len(self.cases)

    def stats(self) -> Dict[str, Any]:
        """케이스 수, 카테고리, 평균 만족도 통계를 반환한다."""
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
        """메모리 캐시에서 식별자가 일치하는 케이스를 찾는다."""
        for c in self.cases:
            if c.metadata.case_id == case_id:
                return c
        return None

    @staticmethod
    def _case_id_from_weaviate(props: Dict[str, Any], uuid: str) -> str:
        """프로퍼티의 원본 식별자를 우선 복원하고 없으면 UUID를 사용한다.

        ``sourceLogId``와 ``postgresId``, ``metadataJson`` 내부 식별자 순으로
        확인해 서로 다른 Experience 스키마 버전을 함께 지원한다.
        """
        source_id = props.get("sourceLogId") or props.get("postgresId")
        if source_id:
            return str(source_id)
        try:
            meta_data = json.loads(props.get("metadataJson", "{}"))
            case_id = meta_data.get("metadata", {}).get("case_id")
            if case_id:
                return str(case_id)
        except Exception:
            pass
        return uuid

    @staticmethod
    def _problem_to_text(problem: ProblemFeatures) -> str:
        """문제 정의를 하이브리드 검색용 단일 텍스트로 합친다."""
        parts = [problem.request]
        if problem.category:
            parts.append(f"카테고리: {problem.category}")
        if problem.keywords:
            parts.append(" ".join(problem.keywords))
        return " | ".join(parts)

    def _case_to_weaviate(self, case: Case) -> Dict[str, Any]:
        """Case → Weaviate Experience 프로퍼티.

        chatbotId 를 비워두면 retrieve 가 어느 에이전트의 케이스인지 구분할 수
        없어 모든 에이전트가 한 풀을 공유하게 된다(치과 봇 절차가 위키 봇 힌트로
        섞이는 식). 값이 있을 때만 스코프가 성립한다.
        """
        props: Dict[str, Any] = {
            "chatbotId": self.chatbot_id,
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
        # 공용 컬렉션에서만 종류를 구분해야 한다. 종류별 컬렉션에는 이 속성이
        # 없어서, 넣으면 auto-schema 가 UI 쪽 컬렉션에 없던 필드를 만들어버린다.
        if self._is_shared_collection:
            props["experienceType"] = EXPERIENCE_TYPE
        return props

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
        """직렬화된 딕셔너리를 중첩된 Case 데이터클래스로 복원한다."""
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
