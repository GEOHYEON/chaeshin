"""
Chaeshin MCP Server — Claude Code 연동.

공식 MCP Python SDK (FastMCP) 사용.

셋업:
    pip install chaeshin
    chaeshin setup claude-code

또는 수동:
    claude mcp add chaeshin -- python -m chaeshin.integrations.claude_code.mcp_server

제공 MCP Tools:
    - chaeshin_retrieve:   유사 케이스 검색 (성공/실패/대기 분리)
    - chaeshin_retain:     실행 패턴 저장 (재귀적 깊이, 기본 outcome=pending)
    - chaeshin_update:     diff 기반 부분 수정 (Update, metadata/outcome 등)
    - chaeshin_revise:     이 레이어의 Tool Graph 교체 + 다운스트림 파급 (고아 자식 처리)
    - chaeshin_delete:     케이스 삭제
    - chaeshin_verdict:    사용자 성공/실패 verdict 기록 (pending → success/failure)
    - chaeshin_feedback:   자연어 피드백 기록
    - chaeshin_decompose:  호스트 AI 위임용 재귀 분해 컨텍스트 반환
    - chaeshin_stats:      저장소 통계
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP

from chaeshin.schema import (
    ProblemFeatures,
    Solution,
    Outcome,
    CaseMetadata,
    Case,
    ToolGraph,
    GraphNode,
    GraphEdge,
)
from chaeshin.case_store import CaseStore
from chaeshin.event_log import EventLog
from chaeshin.storage.sqlite_backend import SQLiteBackend


# ── 저장소 설정 ──────────────────────────────────────────────

GLOBAL_DIR = Path(os.path.expanduser("~/.chaeshin"))
GLOBAL_DIR.mkdir(parents=True, exist_ok=True)

_env_store = os.getenv("CHAESHIN_STORE_DIR", "")
LOCAL_DIR: Optional[Path] = Path(_env_store).resolve() if _env_store else None

# DB 경로: 로컬이 있으면 로컬, 없으면 글로벌
_db_dir = LOCAL_DIR if LOCAL_DIR else GLOBAL_DIR
_db_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = _db_dir / "chaeshin.db"


def _get_embed_fn():
    """OpenAI 임베딩 함수 (있으면)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from chaeshin.integrations.openai import OpenAIAdapter
        return OpenAIAdapter(api_key=api_key).embed_fn
    except ImportError:
        return None


# 단일 전역 backend — MCP 서버 수명 동안 재사용.
_backend = SQLiteBackend(DB_PATH)
_event_log = EventLog(_backend)


def _new_store() -> CaseStore:
    """backend에서 상태를 재로드한 CaseStore 생성."""
    return CaseStore(
        embed_fn=_get_embed_fn(),
        similarity_threshold=0.5,
        backend=_backend,
        auto_load=True,
    )


# ═══════════════════════════════════════════════════════════════════════
# FastMCP Server
# ═══════════════════════════════════════════════════════════════════════

mcp = FastMCP("chaeshin")


def _format_case(
    store: CaseStore,
    case: Case,
    score: float,
    include_children: bool = False,
    include_parent: bool = False,
    recursion_depth: int = 0,
) -> Dict[str, Any]:
    g = case.solution.tool_graph
    meta = case.metadata
    derived_depth = store.derive_depth(meta.case_id)
    formatted: Dict[str, Any] = {
        "case_id": meta.case_id,
        "similarity": round(score, 4),
        "request": case.problem_features.request,
        "category": case.problem_features.category,
        "layer": f"L{derived_depth + 1}",
        "graph": {
            "nodes": [
                {"id": n.id, "tool": n.tool, "note": n.note, "params_hint": n.params_hint}
                for n in g.nodes
            ],
            "edges": [
                {"from_node": e.from_node, "to_node": e.to_node, "condition": e.condition}
                for e in g.edges
            ],
        },
        "outcome": {
            "status": getattr(case.outcome, "status", "success" if case.outcome.success else "pending"),
            "success": case.outcome.success,
            "satisfaction": case.outcome.user_satisfaction,
            "error_reason": case.outcome.error_reason,
            "verdict_note": getattr(case.outcome, "verdict_note", ""),
            "verdict_at": getattr(case.outcome, "verdict_at", ""),
        },
    }

    if derived_depth:
        formatted["depth"] = derived_depth
    wait_mode = getattr(meta, "wait_mode", "deadline")
    deadline_at = getattr(meta, "deadline_at", "")
    if deadline_at or wait_mode != "deadline":
        formatted["wait"] = {"mode": wait_mode, "deadline_at": deadline_at}

    parent_id = getattr(meta, "parent_case_id", "")
    if parent_id:
        formatted["parent_case_id"] = parent_id
    fb_count = getattr(meta, "feedback_count", 0)
    if fb_count > 0:
        formatted["feedback_count"] = fb_count
    difficulty = getattr(meta, "difficulty", 0)
    if difficulty > 0:
        formatted["difficulty"] = difficulty

    if include_children and recursion_depth < 6:
        children = store.get_children(meta.case_id)
        if children:
            formatted["children"] = [
                _format_case(
                    store, c, 0.0,
                    include_children=True,
                    recursion_depth=recursion_depth + 1,
                )
                for c in children
            ]

    if include_parent and recursion_depth == 0:
        parent = store.get_parent(meta.case_id)
        if parent:
            formatted["parent"] = _format_case(
                store, parent, 0.0, recursion_depth=recursion_depth + 1,
            )

    return formatted


@mcp.tool()
def chaeshin_retrieve(
    query: str,
    category: str = "",
    keywords: str = "",
    top_k: int = 3,
    top_k_failures: int = 3,
    min_similarity: float = 0.5,
    include_children: bool = False,
    include_parent: bool = False,
    min_feedback_count: int = 0,
) -> str:
    """Search for similar past cases in Chaeshin memory.

    Returns successful cases and failed cases separately.
    Cases below min_similarity are excluded.
    Cascade-load children/parent layers and filter by feedback count.

    Args:
        query: What the user wants to do (natural language)
        category: Task category (optional)
        keywords: Comma-separated keywords for matching
        top_k: Number of successful cases to return (default 3)
        top_k_failures: Number of failed cases to return (default 3)
        min_similarity: Minimum similarity threshold (default 0.5)
        include_children: If true, also return child layer cases for each match
        include_parent: If true, also return parent layer case for each match
        min_feedback_count: Only return cases with at least this many feedbacks
    """
    store = _new_store()

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

    problem = ProblemFeatures(request=query, category=category, keywords=kw_list)
    result = store.retrieve_with_warnings(problem, top_k=top_k, top_k_failures=top_k_failures)

    def _passes_filter(case: Case) -> bool:
        if min_feedback_count <= 0:
            return True
        return getattr(case.metadata, "feedback_count", 0) >= min_feedback_count

    successes = [
        _format_case(store, c, s, include_children=include_children, include_parent=include_parent)
        for c, s in result["cases"]
        if s >= min_similarity and _passes_filter(c)
    ]
    failures = [
        _format_case(store, c, s, include_children=include_children, include_parent=include_parent)
        for c, s in result["warnings"]
        if s >= min_similarity and _passes_filter(c)
    ]

    pending_raw = result.get("pending", [])
    pending = [
        _format_case(store, c, s, include_children=include_children, include_parent=include_parent)
        for c, s in pending_raw
        if s >= min_similarity and _passes_filter(c)
    ]

    _event_log.record(
        "retrieve",
        payload={
            "query": query,
            "category": category,
            "keywords": kw_list,
            "top_k": top_k,
            "min_similarity": min_similarity,
            "n_successes": len(successes),
            "n_failures": len(failures),
            "n_pending": len(pending),
            "match_scores": [s["similarity"] for s in successes],
        },
        case_ids=(
            [s["case_id"] for s in successes]
            + [f["case_id"] for f in failures]
            + [p["case_id"] for p in pending]
        ),
    )

    if not successes and not failures and not pending:
        return json.dumps(
            {"message": "No similar cases found", "total_in_store": len(store.cases)},
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "successes": successes,
            "failures": failures,
            "pending": pending,
            "total_in_store": len(store.cases),
        },
        ensure_ascii=False,
        indent=2,
    )


DEFAULT_DEADLINE_SECONDS = 7200  # 2시간 — verdict 없으면 "중간(pending)"으로 남음


@mcp.tool()
def chaeshin_retain(
    request: str,
    graph: dict,
    category: str = "",
    keywords: str = "",
    summary: str = "",
    parent_case_id: str = "",
    parent_node_id: str = "",
    difficulty: int = 0,
    child_case_ids: str = "",
    wait_mode: str = "deadline",
    deadline_seconds: int = DEFAULT_DEADLINE_SECONDS,
) -> str:
    """Save a tool execution pattern to Chaeshin memory.

    Outcome defaults to **pending** — success/failure is NEVER assumed. The user
    must explicitly give a verdict via `chaeshin_verdict(case_id, status, note)`.
    If no verdict arrives by `deadline_at`, the case stays `pending` (중간 상태).

    Hierarchy:
        Layer/depth are **derived** from the tree topology — never passed in. A case
        with no children is L1 (leaf, atomic tool call). One with children is L{N+1}
        where N is the max child depth. Decompose recursively until every leaf is
        a single tool call. To form a tree, pass `parent_case_id` + `parent_node_id`.

    Args:
        request: Original user request
        graph: Tool execution graph as dict/JSON with nodes and edges
        category: Task category (e.g. "bug-fix", "feature", "ci")
        keywords: Comma-separated keywords for future matching
        summary: Short result summary
        parent_case_id: Parent case ID when building a hierarchy tree
        parent_node_id: Which node in the parent case this case corresponds to
        difficulty: Optional difficulty estimate (for retrieve ranking)
        child_case_ids: Comma-separated direct child case IDs
        wait_mode: "deadline" (default — auto-release after deadline) or "blocking" (wait forever)
        deadline_seconds: Seconds until verdict deadline (default 7200 = 2h). 0 = no deadline.
    """
    store = _new_store()

    graph_data = graph if isinstance(graph, dict) else json.loads(graph)
    nodes = [
        GraphNode(
            id=n.get("id", f"n{i}"),
            tool=n.get("tool", "unknown"),
            params_hint=n.get("params_hint", {}),
            note=n.get("note", ""),
        )
        for i, n in enumerate(graph_data.get("nodes", []))
    ]
    edges = [
        GraphEdge(
            from_node=e.get("from_node", e.get("from", "")),
            to_node=e.get("to_node", e.get("to")),
            condition=e.get("condition"),
        )
        for e in graph_data.get("edges", [])
    ]

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
    child_ids = [c.strip() for c in child_case_ids.split(",") if c.strip()] if child_case_ids else []

    deadline_at = ""
    if wait_mode == "deadline" and deadline_seconds > 0:
        deadline_at = (datetime.now() + timedelta(seconds=deadline_seconds)).isoformat()

    case = Case(
        problem_features=ProblemFeatures(request=request, category=category, keywords=kw_list),
        solution=Solution(tool_graph=ToolGraph(nodes=nodes, edges=edges)),
        outcome=Outcome(
            status="pending",  # verdict 올 때까지 중간 상태
            result_summary=summary,
            tools_executed=len(nodes),
        ),
        metadata=CaseMetadata(
            source="claude_code",
            tags=kw_list + ["claude_code"],
            parent_case_id=parent_case_id,
            parent_node_id=parent_node_id,
            difficulty=difficulty,
            child_case_ids=child_ids,
            wait_mode=wait_mode,
            deadline_at=deadline_at,
        ),
    )

    case_id = store.retain(case)

    if parent_case_id:
        store.link_parent_child(parent_case_id, case.metadata.case_id, parent_node_id)

    derived_depth = store.derive_depth(case_id)
    derived_layer = f"L{derived_depth + 1}"
    _event_log.record(
        "retain",
        payload={
            "request": request,
            "category": category,
            "layer": derived_layer,
            "depth": derived_depth,
            "status": "pending",
            "parent_case_id": parent_case_id,
            "wait_mode": wait_mode,
            "deadline_at": deadline_at,
            "node_count": len(nodes),
        },
        case_ids=[case_id] + ([parent_case_id] if parent_case_id else []),
    )

    return json.dumps(
        {
            "status": "saved",
            "case_id": case_id,
            "outcome_status": "pending",
            "layer": derived_layer,
            "depth": derived_depth,
            "parent_case_id": parent_case_id or None,
            "wait_mode": wait_mode,
            "deadline_at": deadline_at,
            "next_action": (
                "사용자의 성공/실패 verdict를 받으면 chaeshin_verdict(case_id, status, note) 호출. "
                "verdict 없이 deadline 경과 시 pending으로 남음."
            ),
            "total_cases": len(store.cases),
        },
        ensure_ascii=False,
    )


@mcp.tool()
def chaeshin_update(
    case_id: str,
    patch: dict,
) -> str:
    """Update a case with a partial patch (shallow diff merge).

    Only specified sub-fields are replaced. The diff is recorded as an event
    so changes can be audited (and rolled back if we add that later).

    Args:
        case_id: Target case ID
        patch: Partial dict like {"problem_features": {"request": "..."},
               "metadata": {"layer": "L2"}, "outcome": {"status": "success"}}.
               Only existing fields on each section are applied.
    """
    store = _new_store()
    patch_dict = patch if isinstance(patch, dict) else json.loads(patch)
    diff = store.update_case(case_id, patch_dict)
    if diff is None:
        return json.dumps({"error": f"Case not found: {case_id}"}, ensure_ascii=False)

    _event_log.record(
        "update",
        payload={
            "changed_fields": diff["changed_fields"],
            "patch": patch_dict,
        },
        case_ids=[case_id],
    )

    return json.dumps(
        {
            "status": "updated",
            "case_id": case_id,
            "changed_fields": diff["changed_fields"],
        },
        ensure_ascii=False,
    )


@mcp.tool()
def chaeshin_revise(
    case_id: str,
    graph: dict,
    reason: str = "",
    cascade: bool = True,
) -> str:
    """Replace this layer's Tool Graph and cascade the change downstream.

    **Key mental model**: every case stores its own Tool Graph. A node in a parent
    graph is "expanded" by a child case's graph, linked through `parent_node_id`.
    When you edit a parent layer's graph here, any child case whose
    `parent_node_id` no longer appears in the new graph becomes **orphaned**:
    Chaeshin flips that child back to `outcome.status="pending"` with a
    feedback_log entry so a human can decide whether to revise, re-link, or
    delete it.

    Newly-added node ids are returned as `new_nodes` — expansion candidates the
    host AI can then `chaeshin_retain` as deeper-layer children.

    Args:
        case_id: Case whose graph is being revised
        graph: New graph dict with `nodes` (+ optional `edges`)
        reason: Why the graph is being revised (saved to feedback_log)
        cascade: If true, orphan children hanging off removed nodes (default true)
    """
    store = _new_store()
    graph_data = graph if isinstance(graph, dict) else json.loads(graph)
    result = store.revise_graph(
        case_id=case_id,
        nodes=graph_data.get("nodes", []),
        edges=graph_data.get("edges", []),
        cascade=cascade,
        reason=reason,
    )
    if result is None:
        return json.dumps({"error": f"Case not found: {case_id}"}, ensure_ascii=False)

    _event_log.record(
        "revise",
        payload={
            "reason": reason,
            "added_nodes": result["added_nodes"],
            "removed_nodes": result["removed_nodes"],
            "retained_nodes": result["retained_nodes"],
            "orphaned_children": result["orphaned_children"],
        },
        case_ids=[case_id] + result["orphaned_children"],
    )

    return json.dumps(
        {
            "status": "revised",
            "case_id": case_id,
            "added_nodes": result["added_nodes"],
            "removed_nodes": result["removed_nodes"],
            "retained_nodes": result["retained_nodes"],
            "orphaned_children": result["orphaned_children"],
            "next_action": (
                "added_nodes 중 tool 단일 호출이 아닌 것은 chaeshin_retain으로 하위 "
                "케이스를 붙여 확장하세요. orphaned_children은 검토 후 revise/delete/verdict 결정."
            ),
        },
        ensure_ascii=False,
    )


@mcp.tool()
def chaeshin_delete(case_id: str, reason: str = "") -> str:
    """Delete a case from Chaeshin memory.

    Child links become orphaned (their parent_case_id stays but points to a missing case).

    Args:
        case_id: Target case ID to remove
        reason: Optional reason for deletion (goes to event log)
    """
    store = _new_store()
    ok = store.delete_case(case_id)
    if not ok:
        return json.dumps({"error": f"Case not found: {case_id}"}, ensure_ascii=False)

    _event_log.record(
        "delete",
        payload={"reason": reason},
        case_ids=[case_id],
    )

    return json.dumps({"status": "deleted", "case_id": case_id}, ensure_ascii=False)


@mcp.tool()
def chaeshin_verdict(
    case_id: str,
    status: str,
    note: str = "",
    satisfaction: float = 0.0,
) -> str:
    """Record the user's success/failure verdict on a pending case.

    Chaeshin treats success/failure as an authoritative user signal — never inferred.
    Cases without a verdict stay `pending` (the "중간" in-between state).

    Args:
        case_id: Target case ID
        status: "success" or "failure"
        note: Free-form note from the user (quoted feedback preferred)
        satisfaction: 0-1 satisfaction score (optional, for success)
    """
    if status not in ("success", "failure"):
        return json.dumps({"error": "status must be 'success' or 'failure'"}, ensure_ascii=False)
    store = _new_store()
    case = store.set_verdict(case_id, status, note)
    if case is None:
        return json.dumps({"error": f"Case not found: {case_id}"}, ensure_ascii=False)
    if status == "success" and satisfaction > 0:
        case.outcome.user_satisfaction = satisfaction
        store._persist(case)

    _event_log.record(
        "verdict",
        payload={
            "status": status,
            "note": note,
            "satisfaction": case.outcome.user_satisfaction,
        },
        case_ids=[case_id],
    )

    return json.dumps(
        {
            "status": "verdict_recorded",
            "case_id": case_id,
            "outcome_status": status,
            "verdict_at": case.outcome.verdict_at,
        },
        ensure_ascii=False,
    )


@mcp.tool()
def chaeshin_stats() -> str:
    """Get Chaeshin memory store statistics.

    Returns total cases, store path, embedding status, categories, and layer distribution.
    """
    store = _new_store()
    layers: Dict[str, int] = {}
    statuses: Dict[str, int] = {"success": 0, "failure": 0, "pending": 0}
    now = datetime.now()
    overdue_pending = 0
    for c in store.cases:
        layer = store.derive_layer(c.metadata.case_id)
        layers[layer] = layers.get(layer, 0) + 1
        status = getattr(c.outcome, "status", None) or ("success" if c.outcome.success else "pending")
        statuses[status] = statuses.get(status, 0) + 1
        deadline = getattr(c.metadata, "deadline_at", "")
        if status == "pending" and deadline:
            try:
                if datetime.fromisoformat(deadline) < now:
                    overdue_pending += 1
            except ValueError:
                pass

    payload = {
        "total_cases": len(store.cases),
        "db_path": str(DB_PATH),
        "has_embeddings": store.embed_fn is not None,
        "categories": sorted({
            c.problem_features.category for c in store.cases if c.problem_features.category
        }),
        "layers": layers,
        "outcome_status": statuses,
        "overdue_pending": overdue_pending,  # deadline 지난 pending 개수
        "event_count": _backend.event_count(),
    }
    _event_log.record("stats_viewed", payload={"total_cases": payload["total_cases"]})
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
def chaeshin_feedback(
    case_id: str,
    feedback: str,
    feedback_type: str = "auto",
) -> str:
    """Record user feedback on a Chaeshin case.

    Feedback is logged and the case's feedback_count increases, which boosts
    its retrieval priority for future similar queries.

    Args:
        case_id: Target case ID to give feedback on
        feedback: User feedback in natural language (e.g. "이건 더 복잡해", "순서 바꿔")
        feedback_type: One of: escalate, modify, simplify, correct, reject, auto.
            - escalate: "이건 더 복잡해" — push existing graph down one layer
            - modify: "순서 바꿔" — reorder/edit nodes and edges
            - simplify: "이건 한번에 해도 돼" — merge child layers into parent
            - correct: "이 툴 대신 저걸 써" — swap tool nodes
            - reject: "이건 아예 안 해도 돼" — remove nodes
            - auto: host AI decides the feedback type
    """
    store = _new_store()

    case = store.get_case_by_id(case_id)
    if not case:
        return json.dumps({"error": f"Case not found: {case_id}"}, ensure_ascii=False)

    updated = store.add_feedback(case_id, feedback, feedback_type)
    if not updated:
        return json.dumps({"error": "Failed to add feedback"}, ensure_ascii=False)

    derived_layer = store.derive_layer(case_id)
    _event_log.record(
        "feedback",
        payload={
            "feedback_type": feedback_type,
            "feedback": feedback,
            "feedback_count": updated.metadata.feedback_count,
            "layer": derived_layer,
        },
        case_ids=[case_id],
    )

    return json.dumps(
        {
            "status": "feedback_recorded",
            "case_id": case_id,
            "feedback_type": feedback_type,
            "feedback_count": updated.metadata.feedback_count,
            "feedback_log": updated.metadata.feedback_log[-3:],
            "layer": derived_layer,
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def chaeshin_decompose(
    query: str,
    tools: str = "",
    max_depth: int = 4,
) -> str:
    """Return decomposition context so the *host AI* can break the query into L3→L2→L1.

    Chaeshin does NOT call an LLM itself. It returns:
        1) similar cases for reference,
        2) the layer schema to follow,
        3) a retain protocol (what to call next and in what order).

    The caller (Claude Code or another host AI) decomposes the query and
    persists each layer via chaeshin_retain with parent_case_id linkage.

    Args:
        query: User question/request in natural language
        tools: Comma-separated list of available tool names (optional)
        max_depth: Maximum decomposition depth (default 4, max 6)
    """
    store = _new_store()

    tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []
    max_depth = min(max_depth, 6)

    problem = ProblemFeatures(request=query, category="", keywords=[])
    results = store.retrieve_with_warnings(problem, top_k=3, top_k_failures=1)

    matched_cases = []
    for case, score in results.get("cases", []):
        if score < 0.4:
            continue
        meta = case.metadata
        matched_cases.append(
            {
                "case_id": meta.case_id,
                "similarity": round(score, 4),
                "request": case.problem_features.request,
                "layer": store.derive_layer(meta.case_id),
                "difficulty": getattr(meta, "difficulty", 0),
                "feedback_count": getattr(meta, "feedback_count", 0),
                "has_children": bool(getattr(meta, "child_case_ids", [])),
            }
        )

    leaf_rule = (
        "리프 기준: 해당 노드가 available_tools 중 하나로 **한 번의 tool-call**로 완결되면 리프('L1'). "
        "그렇지 않으면 더 세분화된 자식 케이스로 분해. 깊이는 고정 3단계 아님 — tool로 해결 가능할 때까지 계속. "
        "layer/depth 는 retain 시 인자로 넘기지 않는다 — 트리에서 derived."
    )

    retain_protocol = {
        "style": "recursive_tree",
        "leaf_rule": leaf_rule,
        "order": "루트부터 저장하고 반환된 case_id를 자식 retain 의 parent_case_id 로 전달.",
        "linkage": (
            "각 하위 retain 시 parent_case_id에 상위 case_id, parent_node_id에 해당되는 부모 노드 id를 지정하면 "
            "chaeshin이 자동으로 부모-자식 링크를 설정합니다. layer/depth 는 derived — 응답으로 돌려받음."
        ),
        "verdict_rule": (
            "각 chaeshin_retain은 outcome=pending으로 저장됩니다. 사용자가 성공/실패를 말하면 "
            "chaeshin_verdict(case_id, status, note)를 호출하세요. verdict 없이 deadline 경과 시 pending 유지 "
            "— 중간 상태는 허용됩니다."
        ),
        "example_sequence": [
            {
                "step": 1,
                "call": "chaeshin_retain",
                "args": {
                    "request": query,
                    "graph": {"nodes": ["<상위 단계들>"], "edges": ["..."]},
                    "difficulty": "<estimated depth>",
                },
                "note": "루트를 먼저 저장. 한 번에 tool로 해결 가능하면 이 단계에서 끝 (자식이 없으니 자동으로 L1).",
            },
            {
                "step": 2,
                "call": "chaeshin_retain (각 비-leaf 노드마다 재귀)",
                "args": {
                    "parent_case_id": "<상위 case_id>",
                    "parent_node_id": "<상위 그래프의 해당 노드 id>",
                    "graph": {"nodes": ["<더 작은 단계들>"]},
                },
                "note": "각 노드가 여전히 tool 하나로 불가능하면 또 자식으로 분해. 리프가 될 때까지 반복. 부모의 layer 는 자동으로 한 단계 올라감.",
            },
            {
                "step": 3,
                "call": "chaeshin_retain (리프)",
                "args": {
                    "parent_case_id": "<상위 case_id>",
                    "parent_node_id": "<상위 그래프의 해당 노드 id>",
                    "graph": {"nodes": [{"id": "n1", "tool": "Bash", "note": "..."}]},
                },
                "note": "리프: tool 단일 호출 패턴. 자식 없음 → derived layer = L1.",
            },
            {
                "step": 4,
                "call": "chaeshin_verdict (사용자 응답 받으면)",
                "args": {"case_id": "<any case_id>", "status": "success|failure", "note": "<user quote>"},
                "note": "pending → success/failure. 응답이 없으면 생략 — deadline 경과 후에도 pending은 유효한 상태.",
            },
        ],
    }

    estimated_difficulty = max(
        (c["difficulty"] for c in matched_cases), default=0
    )
    should_decompose = estimated_difficulty >= 2 or any(
        c["feedback_count"] >= 3 for c in matched_cases
    )

    _event_log.record(
        "decompose_context",
        payload={
            "query": query,
            "available_tools": tool_list,
            "max_depth": max_depth,
            "n_matched": len(matched_cases),
            "estimated_difficulty": estimated_difficulty,
            "should_decompose": should_decompose,
        },
        case_ids=[c["case_id"] for c in matched_cases],
    )

    layer_schema = {
        "recursive": True,
        "leaf": "자식 없음 → 'L1' (tool 하나로 해결되는 원자 패턴)",
        "composite": "자식 있음 → 'L{max(child depth)+2}' — 깊이는 트리에서 derived",
        "note": "레이어는 고정 3단계가 아님. retain 시 layer/depth 인자는 받지 않음 — parent_case_id 만 넘기면 트리 토폴로지에서 자동 계산.",
    }

    return json.dumps(
        {
            "query": query,
            "available_tools": tool_list,
            "max_depth": max_depth,
            "similar_cases": matched_cases,
            "layer_schema": layer_schema,
            "retain_protocol": retain_protocol,
            "estimated_difficulty": estimated_difficulty,
            "should_decompose": should_decompose,
            "next_action": (
                "호스트 AI가 query를 재귀적으로 분해 (tool 하나로 가능해질 때까지). "
                "루트부터 저장하며 각 하위는 parent_case_id로 연결. 사용자 verdict가 오면 chaeshin_verdict로 기록."
            ),
            "total_in_store": len(store.cases),
        },
        ensure_ascii=False,
        indent=2,
    )


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
