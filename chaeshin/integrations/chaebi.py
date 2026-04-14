"""
Chaebi Marketplace integration for Chaeshin.

Enables pulling verified cases from the marketplace and pushing learned cases back.
Bidirectional sync: chaeshin <-> chaebi.
"""

from __future__ import annotations

import structlog
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import httpx

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


class ChaebiClient:
    """Chaebi 마켓플레이스 REST 클라이언트.

    Usage:
        async with ChaebiClient("https://chaebi.example.com", "chb_...") as client:
            cases = await client.pull_cases(category="medical")
            await client.push_cases(learned_cases, source="chaeshin_auto")
    """

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    # ── Pull: chaebi → chaeshin ──────────────────────────────────

    async def pull_cases(
        self,
        category: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> List[Case]:
        """Pull approved cases from chaebi marketplace, returned as Chaeshin Case objects.

        Args:
            category: 카테고리 필터 (예: "medical", "cooking")
            since: ISO8601 타임스탬프 — 이후에 업데이트된 케이스만
            limit: 최대 반환 개수

        Returns:
            Chaeshin Case 객체 리스트
        """
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        if since:
            params["since"] = since

        resp = await self._client.get("/api/chaeshin/sync", params=params)
        resp.raise_for_status()

        raw_cases = resp.json().get("cases", [])
        cases = []
        for raw in raw_cases:
            try:
                cases.append(_dict_to_case(raw))
            except Exception as e:
                logger.warning("chaebi_case_parse_failed", error=str(e), raw_keys=list(raw.keys()))
                continue

        logger.info("chaebi_pull_complete", count=len(cases), category=category)
        return cases

    async def pull_raw(
        self,
        category: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Pull cases as raw dicts (Chaeshin JSON format)."""
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        if since:
            params["since"] = since

        resp = await self._client.get("/api/chaeshin/sync", params=params)
        resp.raise_for_status()
        return resp.json().get("cases", [])

    # ── Push: chaeshin → chaebi ──────────────────────────────────

    async def push_cases(
        self,
        cases: List[Case],
        source: str = "chaeshin_auto",
    ) -> Dict[str, Any]:
        """Push learned cases to chaebi for review/publication.

        Args:
            cases: Chaeshin Case 객체 리스트
            source: 출처 식별자 (예: "chaeshin_auto", "chaeshin_manual")

        Returns:
            {"imported": int, "updated": int, "errors": list[str]}
        """
        payload = {
            "cases": [asdict(case) for case in cases],
            "source": source,
        }

        resp = await self._client.post("/api/chaeshin/sync", json=payload)
        resp.raise_for_status()

        result = resp.json()
        logger.info(
            "chaebi_push_complete",
            imported=result.get("imported", 0),
            updated=result.get("updated", 0),
            errors=len(result.get("errors", [])),
        )
        return result

    # ── Export: 특정 케이스 ID로 export ─────────────────────────

    async def export_cases(
        self,
        ids: Optional[List[str]] = None,
        category: Optional[str] = None,
        status: str = "APPROVED",
    ) -> List[Case]:
        """Export cases from chaebi in Chaeshin format.

        Args:
            ids: 특정 케이스 ID 리스트
            category: 카테고리 필터
            status: 상태 필터 (기본: APPROVED)

        Returns:
            Chaeshin Case 객체 리스트
        """
        params: Dict[str, Any] = {}
        if ids:
            params["ids"] = ",".join(ids)
        else:
            if category:
                params["category"] = category
            params["status"] = status

        resp = await self._client.get("/api/chaeshin/export", params=params)
        resp.raise_for_status()

        raw_cases = resp.json().get("cases", [])
        return [_dict_to_case(raw) for raw in raw_cases]

    # ── Lifecycle ────────────────────────────────────────────────

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# ── Helper: dict → Case 변환 ─────────────────────────────────────

def _dict_to_case(d: Dict[str, Any]) -> Case:
    """Chaeshin JSON dict → Case 객체.

    chaebi API 응답의 Chaeshin 형식 dict를 Case 데이터클래스로 변환.
    """
    pf_data = d.get("problem_features", {})
    pf = ProblemFeatures(
        request=pf_data.get("request", ""),
        category=pf_data.get("category", ""),
        keywords=pf_data.get("keywords", []),
        constraints=pf_data.get("constraints", []),
        context=pf_data.get("context", {}),
    )

    tg_data = d.get("solution", {}).get("tool_graph", {})
    tg = ToolGraph(
        nodes=[
            GraphNode(
                id=n.get("id", f"n{i}"),
                tool=n.get("tool", "unknown"),
                params_hint=n.get("params_hint", {}),
                note=n.get("note", ""),
                input_schema=n.get("input_schema", {}),
                output_schema=n.get("output_schema", {}),
            )
            for i, n in enumerate(tg_data.get("nodes", []))
        ],
        edges=[
            GraphEdge(
                from_node=e.get("from_node", ""),
                to_node=e.get("to_node"),
                condition=e.get("condition"),
                action=e.get("action"),
                priority=e.get("priority", 0),
                note=e.get("note", ""),
            )
            for e in tg_data.get("edges", [])
        ],
        parallel_groups=tg_data.get("parallel_groups", []),
        entry_nodes=tg_data.get("entry_nodes", []),
        max_loops=tg_data.get("max_loops", 3),
    )

    out_data = d.get("outcome", {})
    out = Outcome(
        success=out_data.get("success", False),
        result_summary=out_data.get("result_summary", ""),
        tools_executed=out_data.get("tools_executed", 0),
        loops_triggered=out_data.get("loops_triggered", 0),
        total_time_ms=out_data.get("total_time_ms", 0),
        user_satisfaction=out_data.get("user_satisfaction", 0.0),
        error_reason=out_data.get("error_reason", ""),
    )

    meta_data = d.get("metadata", {})
    meta = CaseMetadata(
        case_id=meta_data.get("case_id", ""),
        created_at=meta_data.get("created_at", ""),
        updated_at=meta_data.get("updated_at", ""),
        used_count=meta_data.get("used_count", 0),
        avg_satisfaction=meta_data.get("avg_satisfaction", 0.0),
        source=meta_data.get("source", "chaebi"),
        version=meta_data.get("version", 1),
        tags=meta_data.get("tags", []),
    )

    return Case(
        problem_features=pf,
        solution=Solution(tool_graph=tg),
        outcome=out,
        metadata=meta,
    )
