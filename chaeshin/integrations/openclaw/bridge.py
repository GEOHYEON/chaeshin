"""
OpenClaw ↔ Chaeshin 브리지.

OpenClaw Skill에서 subprocess로 호출되는 CLI 인터페이스.
JSON 입출력으로 tool graph 검색/저장.

Usage:
    # 유사 케이스 검색
    python -m chaeshin.integrations.openclaw.bridge retrieve "김치찌개 만들어줘"

    # 케이스 저장
    python -m chaeshin.integrations.openclaw.bridge retain \\
        --request "김치찌개 2인분" \\
        --category "cooking" \\
        --keywords "kimchi,stew" \\
        --graph '{"nodes":[...],"edges":[...]}'

    # 저장소 통계
    python -m chaeshin.integrations.openclaw.bridge stats
"""

import argparse
import json
import os
import sys

# 프로젝트 루트 자동 탐지
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

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

# ── 저장소 경로 ──
GLOBAL_STORE_DIR = os.path.expanduser("~/.chaeshin")
GLOBAL_STORE_FILE = os.path.join(GLOBAL_STORE_DIR, "cases.json")

_env_store = os.getenv("CHAESHIN_STORE_DIR", "")
LOCAL_STORE_DIR = os.path.abspath(_env_store) if _env_store else None
LOCAL_STORE_FILE = os.path.join(LOCAL_STORE_DIR, "cases.json") if LOCAL_STORE_DIR else None


def _get_embed_fn():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from chaeshin.integrations.openai import OpenAIAdapter
        return OpenAIAdapter(api_key=api_key).embed_fn
    except ImportError:
        return None


def _get_store() -> CaseStore:
    """글로벌 + 로컬 저장소 병합 로드."""
    store = CaseStore(embed_fn=_get_embed_fn(), similarity_threshold=0.5)

    # 글로벌 먼저
    if os.path.exists(GLOBAL_STORE_FILE):
        with open(GLOBAL_STORE_FILE, "r", encoding="utf-8") as f:
            store.load_json(f.read())

    # 로컬 추가 (중복은 로컬 우선)
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
    """저장: 로컬이 있으면 로컬에, 아니면 글로벌에."""
    target_dir = LOCAL_STORE_DIR or GLOBAL_STORE_DIR
    target_file = LOCAL_STORE_FILE or GLOBAL_STORE_FILE
    os.makedirs(target_dir, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(store.to_json())


def cmd_retrieve(args):
    """유사 케이스 검색."""
    store = _get_store()

    problem = ProblemFeatures(
        request=args.query,
        category=args.category or "",
        keywords=[k.strip() for k in (args.keywords or "").split(",") if k.strip()],
    )

    results = store.retrieve(problem, top_k=args.top_k)

    output = []
    for case, score in results:
        graph = case.solution.tool_graph
        output.append({
            "case_id": case.metadata.case_id,
            "similarity": round(score, 4),
            "request": case.problem_features.request,
            "category": case.problem_features.category,
            "graph": {
                "nodes": [
                    {"id": n.id, "tool": n.tool, "params_hint": n.params_hint, "note": n.note}
                    for n in graph.nodes
                ],
                "edges": [
                    {"from": e.from_node, "to": e.to_node, "condition": e.condition, "action": e.action}
                    for e in graph.edges
                ],
            },
            "outcome": {
                "success": case.outcome.success,
                "satisfaction": case.outcome.user_satisfaction,
                "tools_executed": case.outcome.tools_executed,
            },
        })

    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_retain(args):
    """케이스 저장."""
    store = _get_store()

    # 그래프 파싱
    graph_data = json.loads(args.graph) if args.graph else {"nodes": [], "edges": []}
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
            from_node=e.get("from", ""),
            to_node=e.get("to"),
            condition=e.get("condition"),
            action=e.get("action"),
        )
        for e in graph_data.get("edges", [])
    ]
    graph = ToolGraph(nodes=nodes, edges=edges)

    kw_list = [k.strip() for k in (args.keywords or "").split(",") if k.strip()]

    success = getattr(args, "success", True)
    error_reason = getattr(args, "error_reason", "") or ""

    case = Case(
        problem_features=ProblemFeatures(
            request=args.request,
            category=args.category or "",
            keywords=kw_list,
        ),
        solution=Solution(tool_graph=graph),
        outcome=Outcome(
            success=success,
            result_summary=args.summary or f"{args.request} {'완료' if success else '실패'}",
            tools_executed=len(nodes),
            user_satisfaction=args.satisfaction if success else 0.0,
            error_reason=error_reason,
        ),
        metadata=CaseMetadata(
            source="openclaw",
            tags=kw_list + ["openclaw"] + (["failure"] if not success else []),
        ),
    )

    if success:
        case_id = store.retain(case)
    else:
        case_id = store.retain_failure(case, error_reason)
    _save_store(store)

    print(json.dumps({
        "status": "saved",
        "case_id": case_id,
        "success": success,
        "total_cases": len(store.cases),
    }, ensure_ascii=False))


def cmd_stats(args):
    """저장소 통계."""
    store = _get_store()
    print(json.dumps({
        "total_cases": len(store.cases),
        "store_path": STORE_FILE,
        "has_embeddings": store.embed_fn is not None,
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Chaeshin ↔ OpenClaw Bridge"
    )
    sub = parser.add_subparsers(dest="command")

    # retrieve
    p_ret = sub.add_parser("retrieve", help="유사 케이스 검색")
    p_ret.add_argument("query", help="검색 쿼리")
    p_ret.add_argument("--category", default="")
    p_ret.add_argument("--keywords", default="")
    p_ret.add_argument("--top-k", type=int, default=3)
    p_ret.set_defaults(func=cmd_retrieve)

    # retain
    p_save = sub.add_parser("retain", help="케이스 저장")
    p_save.add_argument("--request", required=True)
    p_save.add_argument("--category", default="")
    p_save.add_argument("--keywords", default="")
    p_save.add_argument("--graph", default="{}")
    p_save.add_argument("--summary", default="")
    p_save.add_argument("--satisfaction", type=float, default=0.85)
    p_save.add_argument("--success", dest="success", action="store_true", default=True, help="성공 케이스 (기본값)")
    p_save.add_argument("--no-success", dest="success", action="store_false", help="실패 케이스로 저장")
    p_save.add_argument("--error-reason", default="", help="실패 사유")
    p_save.set_defaults(func=cmd_retain)

    # stats
    p_stats = sub.add_parser("stats", help="저장소 통계")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
