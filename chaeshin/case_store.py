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
import uuid
import structlog
from copy import deepcopy
from datetime import datetime
from dataclasses import asdict, fields as dataclass_fields
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple

from chaeshin.schema import (
    Case,
    ProblemFeatures,
    Solution,
    Outcome,
    CaseMetadata,
    GraphEdge,
    GraphNode,
    ToolGraph,
)
from chaeshin.search import (
    build_search_problem,
    lexical_similarity,
    problem_to_search_text,
)
from chaeshin.storage.sqlite_backend import SQLiteBackend

logger = structlog.get_logger(__name__)


class CaseStore:
    """CBR 케이스 저장소.

    in-memory 리스트 + 선택적 SQLite 영속화.
    backend=None이면 순수 in-memory (기존 테스트 호환).
    """

    def __init__(
        self,
        embed_fn: Optional[Callable[[str], List[float]]] = None,
        similarity_threshold: float = 0.7,
        backend: Optional[SQLiteBackend] = None,
        auto_load: bool = True,
    ):
        """
        Args:
            embed_fn: 텍스트 → 임베딩 벡터 변환 함수 (None이면 키워드 매칭)
            similarity_threshold: 유사도 임계값
            backend: SQLite 영속화 백엔드 (None이면 in-memory only)
            auto_load: backend 지정 시 생성 즉시 기존 케이스 로드
        """
        self.cases: List[Case] = []
        self.embed_fn = embed_fn
        self.similarity_threshold = similarity_threshold
        self._embeddings: Dict[str, List[float]] = {}  # case_id → embedding
        self.backend = backend

        if backend is not None and auto_load:
            self._load_from_backend()

    @staticmethod
    def _ensure_revision_metadata(case: Case):
        """신규/레거시 케이스의 버전 메타 기본값을 정규화."""
        meta = case.metadata
        if not getattr(meta, "root_case_id", ""):
            meta.root_case_id = meta.case_id
        if not hasattr(meta, "is_head"):
            meta.is_head = True
        if not hasattr(meta, "revision_index"):
            meta.revision_index = 0
        if not hasattr(meta, "previous_case_id"):
            meta.previous_case_id = ""
        if not hasattr(meta, "revision_reason"):
            meta.revision_reason = ""

    def _load_from_backend(self):
        """SQLite에서 케이스와 임베딩 로드."""
        if self.backend is None:
            return
        self.cases = self.backend.load_all_cases()
        self._embeddings = self.backend.load_embeddings()

    def _persist(self, case: Case):
        """케이스 + 임베딩을 backend에 저장 (있으면)."""
        if self.backend is None:
            return
        embedding = self._embeddings.get(case.metadata.case_id)
        self.backend.upsert_case(case, embedding=embedding)

    # ── Retrieve ──────────────────────────────────────────────────────

    def _retrieval_candidates(self) -> List[Case]:
        """검색 후보는 live HEAD만 사용 — snapshot은 history 전용."""
        return [
            case for case in self.cases
            if getattr(case.metadata, "is_head", True)
        ]

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
        if not self._retrieval_candidates():
            return []

        search_problem = build_search_problem(problem)
        if self.embed_fn:
            return self._retrieve_hybrid(search_problem, top_k)
        return self._retrieve_by_keywords(search_problem, top_k)

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
        """렉시컬 유사도 검색 (임베딩 없을 때 fallback)."""
        scored: List[Tuple[Case, float]] = []
        for case in self._retrieval_candidates():
            score = lexical_similarity(problem, case.problem_features) * 0.8
            score += self._quality_score(case) * 0.2
            scored.append((case, round(score, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _retrieve_hybrid(
        self,
        problem: ProblemFeatures,
        top_k: int,
    ) -> List[Tuple[Case, float]]:
        """벡터 + 렉시컬 + 메타 신호를 섞은 하이브리드 검색.

        final_score = dense * 0.6 + lexical * 0.3 + quality * 0.1
        임베딩이 없는 legacy case도 lexical 점수로 검색 후보에 남긴다.
        """
        query_text = problem_to_search_text(problem)
        try:
            query_vec = self.embed_fn(query_text) if self.embed_fn else []
        except Exception as e:
            logger.warning("query_embedding_failed", error=str(e))
            return self._retrieve_by_keywords(problem, top_k)

        scored: List[Tuple[Case, float]] = []
        for case in self._retrieval_candidates():
            case_id = case.metadata.case_id
            dense_score = 0.0
            if query_vec and case_id in self._embeddings:
                dense_score = self._cosine_similarity(query_vec, self._embeddings[case_id])

            text_score = lexical_similarity(problem, case.problem_features)
            final_score = dense_score * 0.6 + text_score * 0.3 + self._quality_score(case) * 0.1

            scored.append((case, round(final_score, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _quality_score(self, case: Case) -> float:
        """검색 랭킹용 품질 신호. 성공/실패 bucket 분리는 별도 단계에서 한다."""
        satisfaction = max(0.0, min(1.0, case.outcome.user_satisfaction))
        feedback_count = getattr(case.metadata, "feedback_count", 0)
        feedback_weight = min(feedback_count / 10.0, 1.0) if feedback_count > 0 else 0.0
        return max(satisfaction, feedback_weight)

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
        self._ensure_revision_metadata(case)
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
                text = problem_to_search_text(build_search_problem(case.problem_features))
                self._embeddings[case.metadata.case_id] = self.embed_fn(text)
            except Exception as e:
                logger.warning(
                    "embedding_failed",
                    case_id=case.metadata.case_id,
                    error=str(e),
                )

        self._persist(case)
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
        case.outcome.status = "failure"
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

        # 전체 케이스에 대해 유사도 계산. retrieve()가 사용자 입력을 검색 프로파일로
        # 보강하고, 임베딩이 있으면 하이브리드 랭킹을 적용한다.
        all_results = self.retrieve(problem, top_k=len(self.cases))

        def _status(c: Case) -> str:
            return getattr(c.outcome, "status", None) or ("success" if c.outcome.success else "pending")

        successes = [(c, s) for c, s in all_results if _status(c) == "success"]
        failures = [
            (c, s) for c, s in all_results
            if _status(c) == "failure" and s >= warning_threshold
        ]
        pendings = [
            (c, s) for c, s in all_results
            if _status(c) == "pending" and s >= warning_threshold
        ]

        return {
            "cases": successes[:top_k],
            "warnings": failures[:top_k_failures],
            "pending": pendings[:top_k],
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
        if self.backend is not None:
            self.backend.delete_case(failure_case_id)

        logger.info(
            "failure_promoted",
            old_case_id=failure_case_id,
            new_case_id=successful_case.metadata.case_id,
        )

        # 성공 케이스 저장
        return self.retain(successful_case)

    # ── Hierarchy (계층 연쇄 로드) ──────────────────────────────────

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

    # ── Derived layer / depth ─────────────────────────────────────────

    def derive_depth(self, case_id: str, _visited: Optional[Set[str]] = None) -> int:
        """리프로부터의 거리. 자식 없으면 0, 있으면 1 + max(자식 depth).

        ``parent_case_id`` 만 저장하고 layer/depth 는 항상 트리에서 계산 — 다운스트림이
        깊어지면 자동 반영. 사이클 방어.
        """
        if _visited is None:
            _visited = set()
        if case_id in _visited:
            return 0
        _visited.add(case_id)
        children = self.get_children(case_id)
        if not children:
            return 0
        return 1 + max(self.derive_depth(c.metadata.case_id, _visited) for c in children)

    def derive_layer(self, case_id: str) -> str:
        """``f"L{derive_depth+1}"`` — leaf=L1, composite=L2/L3/...."""
        return f"L{self.derive_depth(case_id) + 1}"

    # ── Diff 기반 Update & Verdict ────────────────────────────────────

    def update_case(self, case_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """케이스를 diff로 업데이트 (얕은 merge).

        patch는 `{"problem_features": {...}, "solution": {...}, "outcome": {...}, "metadata": {...}}`
        형태 — 지정된 하위 키만 얕게 교체. 변경된 필드를 diff로 반환.

        Returns:
            {"before": {...}, "after": {...}, "changed_fields": [...]} 또는 None (미존재).
        """
        case = self.get_case_by_id(case_id)
        if not case:
            return None

        before = {
            "problem_features": asdict(case.problem_features),
            "solution": asdict(case.solution),
            "outcome": asdict(case.outcome),
            "metadata": asdict(case.metadata),
        }

        changed: List[str] = []
        for section, updates in (patch or {}).items():
            if not isinstance(updates, dict):
                continue
            target = getattr(case, section, None)
            if target is None:
                continue
            for k, v in updates.items():
                if not hasattr(target, k):
                    continue
                if getattr(target, k) != v:
                    setattr(target, k, v)
                    changed.append(f"{section}.{k}")

        case.metadata.updated_at = datetime.now().isoformat()

        # Outcome status/success 동기화
        if isinstance(case.outcome.status, str):
            case.outcome.success = case.outcome.status == "success"

        after = {
            "problem_features": asdict(case.problem_features),
            "solution": asdict(case.solution),
            "outcome": asdict(case.outcome),
            "metadata": asdict(case.metadata),
        }

        self._persist(case)
        logger.info("case_updated", case_id=case_id, changed_fields=changed)
        return {"before": before, "after": after, "changed_fields": changed}

    def delete_case(self, case_id: str) -> bool:
        """케이스 삭제. 자식 링크는 그대로 남음 (parent_case_id가 고아가 됨)."""
        idx = None
        for i, c in enumerate(self.cases):
            if c.metadata.case_id == case_id:
                idx = i
                break
        if idx is None:
            return False
        self.cases.pop(idx)
        self._embeddings.pop(case_id, None)
        if self.backend is not None:
            self.backend.delete_case(case_id)
        logger.info("case_deleted", case_id=case_id)
        return True

    @staticmethod
    def _graph_from_parts(
        nodes: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
    ) -> ToolGraph:
        """dict 입력을 ToolGraph로 변환. 알려진 GraphNode/GraphEdge 필드만 반영."""
        node_fields = {f.name for f in dataclass_fields(GraphNode)}
        edge_fields = {f.name for f in dataclass_fields(GraphEdge)}

        graph_nodes: List[GraphNode] = []
        for i, raw in enumerate(nodes or []):
            n = dict(raw or {})
            data = {k: v for k, v in n.items() if k in node_fields}
            data.setdefault("id", f"n{i}")
            data.setdefault("tool", "unknown")
            graph_nodes.append(GraphNode(**data))

        graph_edges: List[GraphEdge] = []
        for raw in edges or []:
            e = dict(raw or {})
            if "from" in e and "from_node" not in e:
                e["from_node"] = e["from"]
            if "to" in e and "to_node" not in e:
                e["to_node"] = e["to"]
            data = {k: v for k, v in e.items() if k in edge_fields}
            data.setdefault("from_node", "")
            data.setdefault("to_node", None)
            graph_edges.append(GraphEdge(**data))

        return ToolGraph(
            nodes=graph_nodes,
            edges=graph_edges,
        )

    @staticmethod
    def _graph_diff(before: ToolGraph, after: ToolGraph) -> Dict[str, Any]:
        """두 ToolGraph의 구조 차이를 node id와 edge dict 기준으로 계산."""
        before_node_ids = [n.id for n in before.nodes]
        after_node_ids = [n.id for n in after.nodes]
        before_node_map = {n.id: asdict(n) for n in before.nodes}
        after_node_map = {n.id: asdict(n) for n in after.nodes}

        retained = [nid for nid in before_node_ids if nid in after_node_map]
        added = [nid for nid in after_node_ids if nid not in before_node_map]
        removed = [nid for nid in before_node_ids if nid not in after_node_map]
        changed = [
            nid for nid in retained
            if before_node_map.get(nid) != after_node_map.get(nid)
        ]

        before_edges = [asdict(e) for e in before.edges]
        after_edges = [asdict(e) for e in after.edges]
        before_edge_keys = {json.dumps(e, sort_keys=True, ensure_ascii=False) for e in before_edges}
        after_edge_keys = {json.dumps(e, sort_keys=True, ensure_ascii=False) for e in after_edges}
        added_edges = [
            e for e in after_edges
            if json.dumps(e, sort_keys=True, ensure_ascii=False) not in before_edge_keys
        ]
        removed_edges = [
            e for e in before_edges
            if json.dumps(e, sort_keys=True, ensure_ascii=False) not in after_edge_keys
        ]

        return {
            "before_nodes": before_node_ids,
            "after_nodes": after_node_ids,
            "retained_nodes": retained,
            "added_nodes": added,
            "removed_nodes": removed,
            "changed_nodes": changed,
            "added_edges": added_edges,
            "removed_edges": removed_edges,
        }

    def _commit_graph_revision(
        self,
        case: Case,
        new_graph: ToolGraph,
        cascade: bool = True,
        reason: str = "",
    ) -> Dict[str, Any]:
        """현재 HEAD를 snapshot으로 보존한 뒤 HEAD 그래프를 새 버전으로 교체."""
        self._ensure_revision_metadata(case)
        before_graph = deepcopy(case.solution.tool_graph)
        diff = self._graph_diff(before_graph, new_graph)
        now = datetime.now().isoformat()

        snapshot = deepcopy(case)
        snapshot.metadata.case_id = str(uuid.uuid4())
        snapshot.metadata.is_head = False
        snapshot.metadata.root_case_id = case.metadata.root_case_id or case.metadata.case_id
        snapshot.metadata.previous_case_id = getattr(case.metadata, "previous_case_id", "") or ""
        # snapshot의 revision_index/reason은 복사된 과거 버전의 값을 유지한다.
        self.cases.append(snapshot)
        self._persist(snapshot)

        case.solution.tool_graph = deepcopy(new_graph)
        case.metadata.previous_case_id = snapshot.metadata.case_id
        case.metadata.revision_index = getattr(case.metadata, "revision_index", 0) + 1
        case.metadata.is_head = True
        case.metadata.root_case_id = case.metadata.root_case_id or case.metadata.case_id
        case.metadata.revision_reason = reason
        case.metadata.updated_at = now

        if reason:
            fb_log = getattr(case.metadata, "feedback_log", []) or []
            fb_log.append(f"[revise] {reason}")
            case.metadata.feedback_log = fb_log

        self._persist(case)

        orphaned: List[str] = []
        if cascade:
            # 자식 중 parent_node_id가 제거된 노드를 가리키면 → 고아화 처리
            for child_id in list(getattr(case.metadata, "child_case_ids", []) or []):
                child = self.get_case_by_id(child_id)
                if not child:
                    continue
                pnode = getattr(child.metadata, "parent_node_id", "")
                if pnode and pnode in diff["removed_nodes"]:
                    child.outcome.status = "pending"
                    child.outcome.success = False
                    child.outcome.verdict_note = (
                        f"parent revised — node '{pnode}' removed from upstream graph"
                    )
                    child.outcome.verdict_at = ""  # 재-verdict 필요
                    fb_log = getattr(child.metadata, "feedback_log", []) or []
                    fb_log.append(
                        f"[cascade] parent node '{pnode}' removed by revise; needs review"
                    )
                    child.metadata.feedback_log = fb_log
                    child.metadata.updated_at = now
                    self._persist(child)
                    orphaned.append(child_id)

        logger.info(
            "graph_revised",
            case_id=case.metadata.case_id,
            snapshot_case_id=snapshot.metadata.case_id,
            revision_index=case.metadata.revision_index,
            added=diff["added_nodes"],
            removed=diff["removed_nodes"],
            retained=len(diff["retained_nodes"]),
            orphaned_children=orphaned,
        )
        return {
            "case_id": case.metadata.case_id,
            "snapshot_case_id": snapshot.metadata.case_id,
            "previous_case_id": case.metadata.previous_case_id,
            "root_case_id": case.metadata.root_case_id,
            "revision_index": case.metadata.revision_index,
            "before_nodes": diff["before_nodes"],
            "after_nodes": diff["after_nodes"],
            "retained_nodes": diff["retained_nodes"],
            "added_nodes": diff["added_nodes"],
            "removed_nodes": diff["removed_nodes"],
            "changed_nodes": diff["changed_nodes"],
            "added_edges": diff["added_edges"],
            "removed_edges": diff["removed_edges"],
            "orphaned_children": orphaned,
            "reason": reason,
        }

    def revise_graph(
        self,
        case_id: str,
        nodes: List[Dict[str, Any]],
        edges: Optional[List[Dict[str, Any]]] = None,
        cascade: bool = True,
        reason: str = "",
    ) -> Optional[Dict[str, Any]]:
        """이 레이어의 Tool Graph를 교체하고, 다운스트림에 파급.

        각 레이어는 자체 Tool Graph를 보유한다. 상위 그래프의 한 노드는 하위 케이스의
        Tool Graph로 "확장"되며 `parent_node_id`로 연결된다. 이 메서드는 특정 레이어
        그래프를 새로 쓰고, 아래 두 가지 downstream 파급을 자동으로 처리한다:

          1. **Orphaned children** — 기존 자식 케이스의 `parent_node_id`가 새 그래프
             nodes에 더 이상 존재하지 않으면, 해당 자식은 "고아"가 된다. 자식의
             `outcome.status`를 `pending`으로 되돌리고, feedback_log에 사유를 남기며,
             이벤트 로그에 기록한다. 자식을 삭제하지는 않음 — 의료/고비용 도메인에서
             의사가 보존할 수도 있으므로 수동 결정이 원칙.

          2. **New expansion candidates** — 이전에 없던 새 노드 id가 추가되면 `new_nodes`
             목록으로 반환. 호스트 AI는 이 노드들을 leaf로 처리할지, 하위 케이스로
             확장할지 결정.

        Args:
            case_id: 수정할 케이스 ID (이 케이스의 그래프를 교체)
            nodes: 새 그래프의 노드 리스트 (GraphNode dict 형식)
            edges: 새 그래프의 엣지 리스트 (선택)
            cascade: True면 자식 고아화/새노드 파급 계산 (기본 True)
            reason: 수정 사유 (feedback_log에 남음)

        Returns:
            {"before": {...}, "after": {...}, "orphaned_children": [...],
             "new_nodes": [...], "retained_nodes": [...]} 또는 None (미존재).
        """
        case = self.get_case_by_id(case_id)
        if not case or not getattr(case.metadata, "is_head", True):
            return None

        new_graph = self._graph_from_parts(
            nodes,
            edges,
        )
        return self._commit_graph_revision(
            case=case,
            new_graph=new_graph,
            cascade=cascade,
            reason=reason,
        )

    def _resolve_head(self, case_id: str) -> Optional[Case]:
        """snapshot ID가 들어와도 같은 revision line의 HEAD를 찾는다."""
        case = self.get_case_by_id(case_id)
        if not case:
            return None
        if getattr(case.metadata, "is_head", True):
            return case

        root_id = getattr(case.metadata, "root_case_id", "") or case.metadata.case_id
        for candidate in self.cases:
            if not getattr(candidate.metadata, "is_head", True):
                continue
            candidate_root = (
                getattr(candidate.metadata, "root_case_id", "")
                or candidate.metadata.case_id
            )
            if candidate_root == root_id:
                return candidate
        return None

    def get_history(self, case_id: str) -> List[Case]:
        """HEAD에서 previous_case_id 체인을 따라 버전 이력을 최신순으로 반환."""
        current = self._resolve_head(case_id) or self.get_case_by_id(case_id)
        if not current:
            return []

        history: List[Case] = []
        visited: Set[str] = set()
        while current:
            cid = current.metadata.case_id
            if cid in visited:
                break
            visited.add(cid)
            history.append(current)
            prev_id = getattr(current.metadata, "previous_case_id", "") or ""
            if not prev_id:
                break
            current = self.get_case_by_id(prev_id)
        return history

    def diff_versions(self, a_id: str, b_id: str) -> Optional[Dict[str, Any]]:
        """두 버전 case_id의 ToolGraph 차이를 반환."""
        a = self.get_case_by_id(a_id)
        b = self.get_case_by_id(b_id)
        if not a or not b:
            return None
        diff = self._graph_diff(a.solution.tool_graph, b.solution.tool_graph)
        return {
            "from_case_id": a_id,
            "to_case_id": b_id,
            "from_revision_index": getattr(a.metadata, "revision_index", 0),
            "to_revision_index": getattr(b.metadata, "revision_index", 0),
            "nodes": {
                "before": diff["before_nodes"],
                "after": diff["after_nodes"],
                "retained": diff["retained_nodes"],
                "added": diff["added_nodes"],
                "removed": diff["removed_nodes"],
                "changed": diff["changed_nodes"],
            },
            "edges": {
                "added": diff["added_edges"],
                "removed": diff["removed_edges"],
            },
        }

    def revert(
        self,
        case_id: str,
        to_index: int,
        cascade: bool = True,
        reason: str = "",
    ) -> Optional[Dict[str, Any]]:
        """지정 revision_index의 그래프를 HEAD에 새 커밋으로 되돌린다."""
        head = self._resolve_head(case_id)
        if not head:
            return None

        target = None
        for version in self.get_history(head.metadata.case_id):
            if getattr(version.metadata, "revision_index", 0) == to_index:
                target = version
                break
        if not target:
            return None

        commit_reason = reason or f"revert to revision {to_index}"
        result = self._commit_graph_revision(
            case=head,
            new_graph=deepcopy(target.solution.tool_graph),
            cascade=cascade,
            reason=commit_reason,
        )
        result["reverted_to_case_id"] = target.metadata.case_id
        result["reverted_to_index"] = to_index
        return result

    def set_verdict(
        self,
        case_id: str,
        status: str,
        note: str = "",
    ) -> Optional[Case]:
        """사용자 verdict 기록 — outcome.status를 success/failure로 전환.

        pending에서만 전환 가능 (재-verdict 가능하게 하려면 force=True 별도).
        note는 verdict_note에 저장.
        """
        if status not in ("success", "failure"):
            raise ValueError(f"verdict status must be 'success' or 'failure', got {status!r}")
        case = self.get_case_by_id(case_id)
        if not case:
            return None
        case.outcome.status = status
        case.outcome.success = status == "success"
        case.outcome.verdict_note = note
        case.outcome.verdict_at = datetime.now().isoformat()
        if status == "failure" and note and not case.outcome.error_reason:
            case.outcome.error_reason = note
        case.metadata.updated_at = datetime.now().isoformat()
        self._persist(case)
        logger.info("verdict_set", case_id=case_id, status=status)
        return case

    # ── Feedback (피드백 반영) ────────────────────────────────────────

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
        self._persist(case)
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

        if self.backend is not None:
            self._persist(parent)
            self._persist(child)
            self.backend.link(parent_case_id, child_case_id, parent_node_id)

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
                self._persist(case)
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
        """딕셔너리 → Case 변환. 미지 키 (legacy layer/depth 등) 는 무시."""
        from chaeshin.schema import (
            GraphNode, GraphEdge, ToolGraph,
            ProblemFeatures, Solution, Outcome, CaseMetadata,
        )

        pf_fields = {f.name for f in dataclass_fields(ProblemFeatures)}
        out_fields = {f.name for f in dataclass_fields(Outcome)}
        meta_fields = {f.name for f in dataclass_fields(CaseMetadata)}

        pf = ProblemFeatures(**{
            k: v for k, v in d["problem_features"].items() if k in pf_fields
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
        out = Outcome(**{k: v for k, v in d["outcome"].items() if k in out_fields})
        meta = CaseMetadata(**{k: v for k, v in d["metadata"].items() if k in meta_fields})

        return Case(
            problem_features=pf,
            solution=sol,
            outcome=out,
            metadata=meta,
        )
