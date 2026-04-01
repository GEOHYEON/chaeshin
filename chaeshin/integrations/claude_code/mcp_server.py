"""
Chaeshin MCP Server — Claude Code 연동.

공식 MCP Python SDK (FastMCP) 사용.

셋업:
    pip install chaeshin
    chaeshin setup claude-code

또는 수동:
    claude mcp add chaeshin -- python -m chaeshin.integrations.claude_code.mcp_server

제공하는 MCP Tools:
    - chaeshin_retrieve:   유사 케이스 검색 (성공 N건 + 실패 N건 분리 반환)
    - chaeshin_retain:     실행 패턴 저장 (성공/실패)
    - chaeshin_stats:      저장소 통계
"""

import json
import os

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

# ── 저장소 설정 ──────────────────────────────────────────────

GLOBAL_STORE_DIR = os.path.expanduser("~/.chaeshin")
GLOBAL_STORE_FILE = os.path.join(GLOBAL_STORE_DIR, "cases.json")

_env_store = os.getenv("CHAESHIN_STORE_DIR", "")
LOCAL_STORE_DIR = os.path.abspath(_env_store) if _env_store else None
LOCAL_STORE_FILE = os.path.join(LOCAL_STORE_DIR, "cases.json") if LOCAL_STORE_DIR else None


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


def _load_store() -> CaseStore:
    """글로벌 + 로컬 저장소 병합 로드."""
    store = CaseStore(embed_fn=_get_embed_fn(), similarity_threshold=0.5)

    if os.path.exists(GLOBAL_STORE_FILE):
        with open(GLOBAL_STORE_FILE, "r", encoding="utf-8") as f:
            store.load_json(f.read())

    if LOCAL_STORE_FILE and os.path.exists(LOCAL_STORE_FILE):
        local = CaseStore(embed_fn=_get_embed_fn(), similarity_threshold=0.5)
        with open(LOCAL_STORE_FILE, "r", encoding="utf-8") as f:
            local.load_json(f.read())
        existing_ids = {c.metadata.case_id for c in store.cases}
        for case in local.cases:
            if case.metadata.case_id in existing_ids:
                store.cases = [c for c in store.cases if c.metadata.case_id != case.metadata.case_id]
            store.cases.append(case)

    return store


def _save_store(store: CaseStore):
    """저장: 로컬이 있으면 로컬에, 없으면 글로벌에."""
    target_dir = LOCAL_STORE_DIR or GLOBAL_STORE_DIR
    target_file = LOCAL_STORE_FILE or GLOBAL_STORE_FILE
    os.makedirs(target_dir, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(store.to_json())


# ═══════════════════════════════════════════════════════════════════════
# FastMCP Server
# ═══════════════════════════════════════════════════════════════════════

mcp = FastMCP("chaeshin")


@mcp.tool()
def chaeshin_retrieve(
    query: str,
    category: str = "",
    keywords: str = "",
    top_k: int = 3,
    top_k_failures: int = 3,
    min_similarity: float = 0.5,
    # === v2 파라미터 ===
    include_children: bool = False,
    include_parent: bool = False,
    min_feedback_count: int = 0,
) -> str:
    """Search for similar past cases in Chaeshin memory.

    Returns successful cases and failed cases separately.
    Cases below min_similarity are excluded.
    v2: can cascade-load children/parent layers and filter by feedback count.

    Args:
        query: What the user wants to do (natural language)
        category: Task category (optional)
        keywords: Comma-separated keywords for matching
        top_k: Number of successful cases to return (default 3)
        top_k_failures: Number of failed cases to return (default 3)
        min_similarity: Minimum similarity threshold — cases below this are not shown (default 0.5)
        include_children: If true, also return child layer cases for each match
        include_parent: If true, also return parent layer case for each match
        min_feedback_count: Only return cases with at least this many feedbacks (0 = no filter)
    """
    store = _load_store()

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []

    problem = ProblemFeatures(request=query, category=category, keywords=kw_list)
    result = store.retrieve_with_warnings(problem, top_k=top_k, top_k_failures=top_k_failures)

    def _format_case(case, score, depth=0):
        g = case.solution.tool_graph
        meta = case.metadata
        formatted = {
            "case_id": meta.case_id,
            "similarity": round(score, 4),
            "request": case.problem_features.request,
            "category": case.problem_features.category,
            "graph": {
                "nodes": [{"id": n.id, "tool": n.tool, "note": n.note, "params_hint": n.params_hint} for n in g.nodes],
                "edges": [{"from_node": e.from_node, "to_node": e.to_node, "condition": e.condition} for e in g.edges],
            },
            "outcome": {
                "success": case.outcome.success,
                "satisfaction": case.outcome.user_satisfaction,
                "error_reason": case.outcome.error_reason,
            },
        }

        # v2 메타 필드 (값이 있을 때만 포함)
        layer = getattr(meta, "layer", "")
        if layer:
            formatted["layer"] = layer
        parent_id = getattr(meta, "parent_case_id", "")
        if parent_id:
            formatted["parent_case_id"] = parent_id
        fb_count = getattr(meta, "feedback_count", 0)
        if fb_count > 0:
            formatted["feedback_count"] = fb_count
        difficulty = getattr(meta, "difficulty", 0)
        if difficulty > 0:
            formatted["difficulty"] = difficulty

        # v2: 하위 레이어 연쇄 로드
        if include_children and depth < 3:
            children = store.get_children(meta.case_id)
            if children:
                formatted["children"] = [
                    _format_case(child, 0.0, depth + 1) for child in children
                ]

        # v2: 상위 레이어 로드
        if include_parent and depth == 0:
            parent = store.get_parent(meta.case_id)
            if parent:
                formatted["parent"] = _format_case(parent, 0.0, depth + 1)

        return formatted

    # v2: feedback_count 필터
    def _passes_filter(case):
        if min_feedback_count <= 0:
            return True
        return getattr(case.metadata, "feedback_count", 0) >= min_feedback_count

    successes = [
        _format_case(c, s) for c, s in result["cases"]
        if s >= min_similarity and _passes_filter(c)
    ]
    failures = [
        _format_case(c, s) for c, s in result["warnings"]
        if s >= min_similarity and _passes_filter(c)
    ]

    if not successes and not failures:
        return json.dumps({"message": "No similar cases found", "total_in_store": len(store.cases)}, ensure_ascii=False)

    return json.dumps({
        "successes": successes,
        "failures": failures,
        "total_in_store": len(store.cases),
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def chaeshin_retain(
    request: str,
    graph: dict,
    category: str = "",
    keywords: str = "",
    summary: str = "",
    satisfaction: float = 0.85,
    success: bool = True,
    error_reason: str = "",
    # === v2 파라미터 ===
    layer: str = "",
    parent_case_id: str = "",
    parent_node_id: str = "",
    difficulty: int = 0,
    child_case_ids: str = "",
) -> str:
    """Save a tool execution pattern to Chaeshin memory for future reuse.

    Save both successful patterns (to reuse) and failed patterns (to avoid).
    v2: supports hierarchical layers — set layer/parent/difficulty for layered storage.

    Args:
        request: Original user request
        graph: Tool execution graph as JSON string with nodes and edges
        category: Task category (e.g. "bug-fix", "feature", "ci")
        keywords: Comma-separated keywords for future matching
        summary: Short result summary
        satisfaction: Satisfaction score 0-1 (default 0.85)
        success: Whether the execution succeeded. Set false to save as anti-pattern.
        error_reason: Why it failed (only when success=false)
        layer: Hierarchy layer — "L1" (tool calls), "L2" (patterns), "L3" (strategy). Empty = flat/legacy.
        parent_case_id: Parent layer case ID (for L1/L2 cases that belong to a higher layer)
        parent_node_id: Which node in the parent case this case corresponds to
        difficulty: Decomposition depth when this case is the root (0 = not calculated)
        child_case_ids: Comma-separated child case IDs (for L2/L3 cases with sub-layers)
    """
    store = _load_store()

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
            # edge 키 호환: "from"/"from_node" 둘 다 지원
            from_node=e.get("from_node", e.get("from", "")),
            to_node=e.get("to_node", e.get("to")),
            condition=e.get("condition"),
        )
        for e in graph_data.get("edges", [])
    ]

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
    child_ids = [c.strip() for c in child_case_ids.split(",") if c.strip()] if child_case_ids else []

    case = Case(
        problem_features=ProblemFeatures(request=request, category=category, keywords=kw_list),
        solution=Solution(tool_graph=ToolGraph(nodes=nodes, edges=edges)),
        outcome=Outcome(
            success=success,
            result_summary=summary,
            tools_executed=len(nodes),
            user_satisfaction=satisfaction if success else 0.0,
            error_reason=error_reason,
        ),
        metadata=CaseMetadata(
            source="claude_code",
            tags=kw_list + ["claude_code"] + (["failure"] if not success else []),
            # v2 필드
            layer=layer,
            parent_case_id=parent_case_id,
            parent_node_id=parent_node_id,
            difficulty=difficulty,
            child_case_ids=child_ids,
        ),
    )

    if success:
        case_id = store.retain(case)
    else:
        case_id = store.retain_failure(case, error_reason)

    # v2: 부모-자식 링크 자동 설정
    if parent_case_id:
        store.link_parent_child(parent_case_id, case.metadata.case_id, parent_node_id)

    _save_store(store)

    return json.dumps({
        "status": "saved",
        "case_id": case_id,
        "success": success,
        "layer": layer or "(flat)",
        "total_cases": len(store.cases),
    }, ensure_ascii=False)


@mcp.tool()
def chaeshin_stats() -> str:
    """Get Chaeshin memory store statistics.

    Returns total cases, store paths, embedding status, and categories.
    """
    store = _load_store()
    return json.dumps({
        "total_cases": len(store.cases),
        "global_store": GLOBAL_STORE_FILE,
        "local_store": LOCAL_STORE_FILE or "(not set)",
        "has_embeddings": store.embed_fn is not None,
        "categories": list(set(c.problem_features.category for c in store.cases if c.problem_features.category)),
    }, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# v2: New Tools
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
def chaeshin_feedback(
    case_id: str,
    feedback: str,
    feedback_type: str = "auto",
) -> str:
    """Record user feedback on a Chaeshin case.

    The Reflection Agent uses this to improve stored cases based on user feedback.
    Feedback is logged and the case's feedback_count increases, which boosts
    its retrieval priority for future similar queries.

    Args:
        case_id: Target case ID to give feedback on
        feedback: User feedback in natural language (e.g. "이건 더 복잡해", "순서 바꿔")
        feedback_type: One of: escalate, modify, simplify, correct, reject, auto.
            - escalate: "이건 더 복잡해" — push existing graph down one layer, create new intermediate layer
            - modify: "순서 바꿔" — reorder/edit nodes and edges in the graph
            - simplify: "이건 한번에 해도 돼" — merge child layers into parent
            - correct: "이 툴 대신 저걸 써" — swap tool nodes
            - reject: "이건 아예 안 해도 돼" — remove nodes
            - auto: LLM decides the feedback type (default)
    """
    store = _load_store()

    case = store.get_case_by_id(case_id)
    if not case:
        return json.dumps({"error": f"Case not found: {case_id}"}, ensure_ascii=False)

    updated = store.add_feedback(case_id, feedback, feedback_type)
    if not updated:
        return json.dumps({"error": "Failed to add feedback"}, ensure_ascii=False)

    _save_store(store)

    return json.dumps({
        "status": "feedback_recorded",
        "case_id": case_id,
        "feedback_type": feedback_type,
        "feedback_count": updated.metadata.feedback_count,
        "feedback_log": updated.metadata.feedback_log[-3:],  # 최근 3개만
        "layer": getattr(updated.metadata, "layer", "") or "(flat)",
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def chaeshin_decompose(
    query: str,
    tools: str = "",
    max_depth: int = 4,
) -> str:
    """Decompose a user query into a hierarchical task tree.

    This is used by the Decomposer Agent to break down complex queries.
    It calculates difficulty (tree depth) and checks Chaeshin for similar cases.

    Args:
        query: User question/request in natural language
        tools: Comma-separated list of available tool names (optional)
        max_depth: Maximum decomposition depth (default 4, max 6)
    """
    store = _load_store()

    tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []
    max_depth = min(max_depth, 6)

    # 유사 케이스 검색 — 쿼리의 추상도에 맞는 레이어가 자연스럽게 매칭됨
    problem = ProblemFeatures(request=query, category="", keywords=[])
    results = store.retrieve_with_warnings(problem, top_k=3, top_k_failures=1)

    matched_cases = []
    for case, score in results.get("cases", []):
        if score < 0.4:
            continue
        meta = case.metadata
        matched_cases.append({
            "case_id": meta.case_id,
            "similarity": round(score, 4),
            "request": case.problem_features.request,
            "layer": getattr(meta, "layer", "") or "(flat)",
            "difficulty": getattr(meta, "difficulty", 0),
            "feedback_count": getattr(meta, "feedback_count", 0),
            "has_children": bool(getattr(meta, "child_case_ids", [])),
        })

    # 난이도 추정: 매칭된 케이스의 difficulty 참고, 없으면 0
    estimated_difficulty = 0
    if matched_cases:
        estimated_difficulty = max(c["difficulty"] for c in matched_cases)

    # 검색 트리거 판단
    should_use_chaeshin = (
        estimated_difficulty >= 2
        or any(c["feedback_count"] >= 3 for c in matched_cases)
    )

    return json.dumps({
        "query": query,
        "available_tools": tool_list,
        "max_depth": max_depth,
        "matched_cases": matched_cases,
        "estimated_difficulty": estimated_difficulty,
        "should_use_chaeshin": should_use_chaeshin,
        "recommendation": (
            "Complex query — use matched cases as reference for decomposition"
            if should_use_chaeshin
            else "Simple query — proceed with direct tool calling or shallow decomposition"
        ),
        "total_in_store": len(store.cases),
    }, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
