"""Bulk seed case generator — LLM 루프 + 임베딩 dedup.

(topic, tool_allowlist, count) → 시드 케이스 N건을 staging store 에 retain.
중복은 임베딩 코사인 유사도로 reject. 실패 시 negative-prompt 재시도 (max 3회).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog

from chaeshin.case_store import CaseStore
from chaeshin.schema import (
    Case,
    CaseMetadata,
    GraphEdge,
    GraphNode,
    Outcome,
    ProblemFeatures,
    Solution,
    ToolGraph,
)
from chaeshin.seed.scenario_prompt import build_scenario_prompt

logger = structlog.get_logger(__name__)


LLMFn = Callable[[List[Dict[str, str]]], Awaitable[str]]
EmbedFn = Callable[[str], List[float]]


@dataclass
class GenerationEvent:
    """생성 루프 1회의 결과 — accept / reject / error 중 하나."""

    kind: str  # "accept" | "reject_duplicate" | "reject_invalid" | "error"
    case_id: str = ""
    request: str = ""
    similarity: float = 0.0
    reason: str = ""
    attempt: int = 0


class BulkGenerator:
    """Topic + tool allowlist → seed Case N건 생성.

    - LLM 호출 → JSON 파싱 → tool allowlist 검증 → 임베딩 dedup → store.retain.
    - Reject 시 negative-prompt addendum 으로 max ``max_attempts_per_case`` 회 재시도.
    - 임베딩 함수가 없으면 키워드 Jaccard fallback (같은 category + Jaccard >= jaccard_threshold).
    """

    def __init__(
        self,
        llm_fn: LLMFn,
        store: CaseStore,
        embed_fn: Optional[EmbedFn] = None,
        similarity_threshold: float = 0.85,
        jaccard_threshold: float = 0.7,
    ):
        self.llm_fn = llm_fn
        self.store = store
        self.embed_fn = embed_fn
        self.similarity_threshold = similarity_threshold
        self.jaccard_threshold = jaccard_threshold

    async def expand_seed_node(
        self,
        parent_case_id: str,
        parent_node_id: str,
        sub_topic: str,
        tool_allowlist: List[str],
        max_attempts: int = 3,
    ) -> Optional[Case]:
        """Seed 트리 빌더 — 부모 케이스의 한 노드를 sub-graph 로 분해해 자식 케이스로 retain.

        주로 monitor UI / CLI 에서 사용자가 "이 노드 expand" 액션을 누를 때 호출하는
        단일-스텝 헬퍼. 트리 깊이 자동 확장은 호스트가 루프로 돌릴 책임.

        Args:
            parent_case_id: 이미 store 에 있는 부모 seed case_id.
            parent_node_id: 부모 graph 안에서 expand 대상이 되는 노드 id.
            sub_topic: 자식 case 의 시나리오 토픽 — 보통 부모 노드의 ``note`` 텍스트.
            tool_allowlist: 자식 graph 에 허용할 도구 이름.
            max_attempts: LLM 재시도 횟수.

        Returns:
            성공 시 자식 ``Case``, 실패 시 ``None``.
        """
        parent = self.store.get_case_by_id(parent_case_id)
        if parent is None:
            logger.warning("seed_expand_parent_not_found", parent_case_id=parent_case_id)
            return None

        in_flight_embeddings: List[List[float]] = []
        in_flight_keywords: List[tuple[str, set]] = []
        marker = f"{getattr(parent.metadata, 'source', 'seed:expand')}:expand"

        for attempt in range(1, max_attempts + 1):
            event = await self._try_one(
                topic=sub_topic,
                tool_allowlist=tool_allowlist,
                sample_seeds=None,
                avoid_themes=None,
                in_flight_embeddings=in_flight_embeddings,
                in_flight_keywords=in_flight_keywords,
                source_marker=marker,
                attempt=attempt,
            )
            if event.kind == "accept":
                child = self.store.get_case_by_id(event.case_id)
                if child is None:
                    return None
                # 부모-자식 링크
                self.store.link_parent_child(
                    parent_case_id, event.case_id, parent_node_id
                )
                logger.info(
                    "seed_expanded",
                    parent_case_id=parent_case_id,
                    parent_node_id=parent_node_id,
                    child_case_id=event.case_id,
                )
                return child
            logger.info(
                "seed_expand_attempt_failed",
                parent_case_id=parent_case_id,
                attempt=attempt,
                kind=event.kind,
            )

        return None

    async def generate(
        self,
        topic: str,
        tool_allowlist: List[str],
        count: int,
        sample_seeds: Optional[List[Dict[str, Any]]] = None,
        max_attempts_per_case: int = 3,
        source_marker: Optional[str] = None,
    ) -> List[Case]:
        """``count`` 개의 시드 케이스를 생성해 store 에 retain.

        Returns:
            성공적으로 retain 된 ``Case`` 리스트.
        """
        marker = source_marker or f"seed:{topic}"
        accepted: List[Case] = []
        in_flight_embeddings: List[List[float]] = []
        in_flight_keywords: List[tuple[str, set]] = []  # (category, keywords)
        recently_rejected: List[str] = []

        for i in range(count):
            avoid = recently_rejected[-3:] if recently_rejected else None
            for attempt in range(1, max_attempts_per_case + 1):
                event = await self._try_one(
                    topic=topic,
                    tool_allowlist=tool_allowlist,
                    sample_seeds=sample_seeds,
                    avoid_themes=avoid,
                    in_flight_embeddings=in_flight_embeddings,
                    in_flight_keywords=in_flight_keywords,
                    source_marker=marker,
                    attempt=attempt,
                )
                if event.kind == "accept":
                    case = self.store.get_case_by_id(event.case_id)
                    if case is not None:
                        accepted.append(case)
                    logger.info(
                        "seed_accepted",
                        topic=topic,
                        case_id=event.case_id,
                        index=i,
                        attempt=attempt,
                    )
                    break
                elif event.kind == "reject_duplicate":
                    if event.request:
                        recently_rejected.append(event.request)
                    logger.info(
                        "seed_rejected_duplicate",
                        topic=topic,
                        index=i,
                        attempt=attempt,
                        similarity=event.similarity,
                    )
                    avoid = recently_rejected[-3:]
                else:
                    logger.warning(
                        "seed_attempt_failed",
                        topic=topic,
                        index=i,
                        attempt=attempt,
                        kind=event.kind,
                        reason=event.reason,
                    )
            else:
                logger.warning(
                    "seed_giving_up", topic=topic, index=i, attempts=max_attempts_per_case
                )

        return accepted

    async def _try_one(
        self,
        topic: str,
        tool_allowlist: List[str],
        sample_seeds: Optional[List[Dict[str, Any]]],
        avoid_themes: Optional[List[str]],
        in_flight_embeddings: List[List[float]],
        in_flight_keywords: List[tuple[str, set]],
        source_marker: str,
        attempt: int,
    ) -> GenerationEvent:
        prompt = build_scenario_prompt(
            topic=topic,
            tool_allowlist=tool_allowlist,
            sample_seeds=sample_seeds,
            avoid_themes=avoid_themes,
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"토픽: {topic}. 시나리오 한 건을 만들어라."},
        ]
        try:
            response = await self.llm_fn(messages)
        except Exception as e:
            return GenerationEvent(kind="error", reason=str(e), attempt=attempt)

        try:
            payload = _parse_json(response)
        except (json.JSONDecodeError, ValueError) as e:
            return GenerationEvent(
                kind="reject_invalid", reason=f"json parse: {e}", attempt=attempt
            )

        validation = _validate_payload(payload, tool_allowlist)
        if validation:
            return GenerationEvent(
                kind="reject_invalid", reason=validation, attempt=attempt
            )

        request = payload["request"].strip()
        category = payload.get("category", "").strip()
        keywords_list = [str(k).strip() for k in payload.get("keywords", []) if str(k).strip()]
        constraints = [str(c).strip() for c in payload.get("constraints", []) if str(c).strip()]

        # Dedup
        text = f"{request} {' '.join(keywords_list)}"
        if self.embed_fn is not None:
            try:
                vec = self.embed_fn(text)
            except Exception as e:
                logger.warning("seed_embed_failed", error=str(e))
                vec = None
            if vec is not None:
                sim = self._max_cosine(vec, in_flight_embeddings)
                stored_sim = self._max_cosine(vec, list(self.store._embeddings.values()))
                top = max(sim, stored_sim)
                if top >= self.similarity_threshold:
                    return GenerationEvent(
                        kind="reject_duplicate",
                        request=request,
                        similarity=top,
                        attempt=attempt,
                    )
                in_flight_embeddings.append(vec)
        else:
            kw_set = set(keywords_list)
            if self._jaccard_collision(category, kw_set, in_flight_keywords):
                return GenerationEvent(
                    kind="reject_duplicate",
                    request=request,
                    similarity=1.0,
                    attempt=attempt,
                )
            in_flight_keywords.append((category, kw_set))

        # Build Case
        nodes = [
            GraphNode(
                id=str(n.get("id", f"n{i}")),
                tool=str(n["tool"]),
                params_hint=n.get("params_hint", {}) or {},
                note=str(n.get("note", "")),
            )
            for i, n in enumerate(payload["graph"]["nodes"])
        ]
        edges = []
        for e in payload["graph"].get("edges", []) or []:
            edges.append(
                GraphEdge(
                    from_node=str(e.get("from_node") or e.get("from") or ""),
                    to_node=(e.get("to_node") if "to_node" in e else e.get("to")),
                    condition=e.get("condition"),
                )
            )
        case = Case(
            problem_features=ProblemFeatures(
                request=request,
                category=category,
                keywords=keywords_list,
                constraints=constraints,
            ),
            solution=Solution(tool_graph=ToolGraph(nodes=nodes, edges=edges)),
            outcome=Outcome(status="pending", tools_executed=len(nodes)),
            metadata=CaseMetadata(
                source=source_marker,
                tags=keywords_list + ["seed"],
            ),
        )
        case_id = self.store.retain(case)
        return GenerationEvent(kind="accept", case_id=case_id, request=request, attempt=attempt)

    @staticmethod
    def _max_cosine(vec: List[float], others: List[List[float]]) -> float:
        if not others:
            return 0.0
        return max(_cosine(vec, o) for o in others)

    def _jaccard_collision(
        self,
        category: str,
        kw: set,
        in_flight: List[tuple[str, set]],
    ) -> bool:
        for c, existing in in_flight:
            if c != category:
                continue
            if not (kw or existing):
                continue
            union = kw | existing
            if not union:
                continue
            jacc = len(kw & existing) / len(union)
            if jacc >= self.jaccard_threshold:
                return True
        # 이미 store 에 있는 케이스도 검사
        for c in self.store.cases:
            if c.problem_features.category != category:
                continue
            existing = set(c.problem_features.keywords)
            union = kw | existing
            if not union:
                continue
            jacc = len(kw & existing) / len(union)
            if jacc >= self.jaccard_threshold:
                return True
        return False


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _parse_json(text: str) -> Dict[str, Any]:
    """LLM 응답에서 JSON 객체를 추출/파싱."""
    fence = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1).strip())
    fence = re.search(r"```\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        if candidate.startswith("{"):
            return json.loads(candidate)
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        return json.loads(brace.group(0))
    raise ValueError("no JSON object found")


def _validate_payload(payload: Dict[str, Any], tool_allowlist: List[str]) -> str:
    """잘못된 시드면 사유 문자열 반환, 유효하면 빈 문자열."""
    if not isinstance(payload, dict):
        return "payload is not a dict"
    if not payload.get("request"):
        return "missing request"
    graph = payload.get("graph")
    if not isinstance(graph, dict):
        return "missing graph"
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return "graph.nodes empty"
    allowed = set(tool_allowlist)
    if allowed:
        for n in nodes:
            tool = n.get("tool")
            if tool not in allowed:
                return f"tool '{tool}' not in allowlist"
    return ""
