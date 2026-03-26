"""
Chaeshin MCP Server — Claude Code 연동.

Claude Code에서 한 줄로 연결:
    claude mcp add chaeshin -- python -m chaeshin.integrations.claude_code.mcp_server

제공하는 MCP Tools:
    - chaeshin_retrieve: 유사 케이스 검색
    - chaeshin_retain:   성공한 실행 패턴 저장
    - chaeshin_stats:    저장소 통계
    - chaeshin_anticipate: 현재 컨텍스트 기반 선제 제안
"""

import json
import os
import sys
from typing import Any

# 프로젝트 루트 자동 탐지
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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

# ── 저장소 설정 ──
# 글로벌 저장소 (항상 존재)
GLOBAL_STORE_DIR = os.path.expanduser("~/.chaeshin")
GLOBAL_STORE_FILE = os.path.join(GLOBAL_STORE_DIR, "cases.json")

# 프로젝트 로컬 저장소 (CHAESHIN_STORE_DIR이 상대경로면 프로젝트별)
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


def _load_single_store(store_file: str) -> CaseStore:
    """단일 저장소 파일 로드."""
    store = CaseStore(embed_fn=_get_embed_fn(), similarity_threshold=0.5)
    if os.path.exists(store_file):
        with open(store_file, "r", encoding="utf-8") as f:
            store.load_json(f.read())
    return store


def _load_store() -> CaseStore:
    """글로벌 + 로컬 저장소 병합 로드.

    검색 시 두 저장소의 케이스를 모두 봄.
    저장 시에는 로컬이 있으면 로컬에, 없으면 글로벌에.
    """
    store = CaseStore(embed_fn=_get_embed_fn(), similarity_threshold=0.5)

    # 글로벌 먼저 로드
    if os.path.exists(GLOBAL_STORE_FILE):
        with open(GLOBAL_STORE_FILE, "r", encoding="utf-8") as f:
            store.load_json(f.read())

    # 로컬이 있으면 추가 로드 (중복 case_id는 로컬이 우선)
    if LOCAL_STORE_FILE and os.path.exists(LOCAL_STORE_FILE):
        local_store = _load_single_store(LOCAL_STORE_FILE)
        existing_ids = {c.metadata.case_id for c in store.cases}
        for case in local_store.cases:
            if case.metadata.case_id in existing_ids:
                # 로컬이 우선 — 글로벌 것을 교체
                store.cases = [c for c in store.cases if c.metadata.case_id != case.metadata.case_id]
            store.cases.append(case)

    return store


def _save_store(store: CaseStore):
    """저장: 로컬이 설정되어 있으면 로컬에, 아니면 글로벌에."""
    target_dir = LOCAL_STORE_DIR or GLOBAL_STORE_DIR
    target_file = LOCAL_STORE_FILE or GLOBAL_STORE_FILE

    os.makedirs(target_dir, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as f:
        f.write(store.to_json())


# ═══════════════════════════════════════════════════════════════════════
# MCP Tool Handlers
# ═══════════════════════════════════════════════════════════════════════

def handle_retrieve(params: dict) -> dict:
    """유사 케이스 검색 — 안티패턴 경고 포함."""
    store = _load_store()
    query = params.get("query", "")
    category = params.get("category", "")
    keywords = params.get("keywords", [])
    top_k = params.get("top_k", 3)

    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    problem = ProblemFeatures(
        request=query,
        category=category,
        keywords=keywords,
    )

    result = store.retrieve_with_warnings(problem, top_k=top_k)

    cases = []
    for case, score in result["cases"]:
        g = case.solution.tool_graph
        cases.append({
            "case_id": case.metadata.case_id,
            "similarity": round(score, 4),
            "request": case.problem_features.request,
            "category": case.problem_features.category,
            "graph": {
                "nodes": [{"id": n.id, "tool": n.tool, "note": n.note, "params_hint": n.params_hint} for n in g.nodes],
                "edges": [{"from": e.from_node, "to": e.to_node, "condition": e.condition} for e in g.edges],
            },
            "outcome": {
                "success": case.outcome.success,
                "satisfaction": case.outcome.user_satisfaction,
            },
        })

    warnings = []
    for case, score in result["warnings"]:
        warnings.append({
            "case_id": case.metadata.case_id,
            "similarity": round(score, 4),
            "request": case.problem_features.request,
            "error_reason": case.outcome.error_reason,
        })

    return {"cases": cases, "warnings": warnings, "total_in_store": len(store.cases)}


def handle_retain(params: dict) -> dict:
    """성공한 실행 패턴 저장."""
    store = _load_store()

    graph_data = params.get("graph", {})
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
        )
        for e in graph_data.get("edges", [])
    ]

    keywords = params.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]

    success = params.get("success", True)
    error_reason = params.get("error_reason", "")

    case = Case(
        problem_features=ProblemFeatures(
            request=params.get("request", ""),
            category=params.get("category", ""),
            keywords=keywords,
        ),
        solution=Solution(tool_graph=ToolGraph(nodes=nodes, edges=edges)),
        outcome=Outcome(
            success=success,
            result_summary=params.get("summary", ""),
            tools_executed=len(nodes),
            user_satisfaction=params.get("satisfaction", 0.85) if success else 0.0,
            error_reason=error_reason,
        ),
        metadata=CaseMetadata(
            source="claude_code",
            tags=keywords + ["claude_code"] + (["failure"] if not success else []),
        ),
    )

    if success:
        case_id = store.retain(case)
    else:
        case_id = store.retain_failure(case, error_reason)
    _save_store(store)

    return {"status": "saved", "case_id": case_id, "success": success, "total_cases": len(store.cases)}


def handle_stats(params: dict) -> dict:
    """저장소 통계."""
    store = _load_store()
    return {
        "total_cases": len(store.cases),
        "global_store": GLOBAL_STORE_FILE,
        "local_store": LOCAL_STORE_FILE or "(not set)",
        "has_embeddings": store.embed_fn is not None,
        "categories": list(set(c.problem_features.category for c in store.cases if c.problem_features.category)),
    }


def handle_anticipate(params: dict) -> dict:
    """현재 컨텍스트 기반 선제 제안."""
    store = _load_store()
    context = params.get("context", "")
    category = params.get("category", "")

    problem = ProblemFeatures(
        request=context,
        category=category,
        keywords=[k.strip() for k in context.split()[:5]],
    )

    results = store.retrieve(problem, top_k=1)
    if not results:
        return {"suggestion": None, "message": "No similar cases found"}

    case, score = results[0]
    if score < 0.6:
        return {"suggestion": None, "message": f"Best match too low (similarity: {score:.3f})"}

    g = case.solution.tool_graph
    return {
        "suggestion": {
            "case_id": case.metadata.case_id,
            "similarity": round(score, 4),
            "request": case.problem_features.request,
            "graph_summary": f"{len(g.nodes)} nodes, {len(g.edges)} edges",
            "first_steps": [
                {"tool": n.tool, "note": n.note}
                for n in g.nodes[:3]
            ],
        },
        "message": f"Found similar case with {score:.1%} similarity",
    }


# ═══════════════════════════════════════════════════════════════════════
# MCP stdio Protocol
# ═══════════════════════════════════════════════════════════════════════

TOOLS = {
    "chaeshin_retrieve": {
        "handler": handle_retrieve,
        "description": "Search for similar past cases in Chaeshin memory. Returns tool execution graphs that worked before.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the user wants to do (natural language)"},
                "category": {"type": "string", "description": "Task category (optional)"},
                "keywords": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string"},
                    ],
                    "description": "Keywords for matching (comma-separated string or array)",
                },
                "top_k": {"type": "integer", "description": "Number of results", "default": 3},
            },
            "required": ["query"],
        },
    },
    "chaeshin_retain": {
        "handler": handle_retain,
        "description": "Save a successful tool execution pattern to Chaeshin memory for future reuse.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "Original user request"},
                "category": {"type": "string", "description": "Task category"},
                "keywords": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string"},
                    ],
                    "description": "Keywords for future matching",
                },
                "graph": {
                    "type": "object",
                    "description": "Tool execution graph with nodes and edges",
                    "properties": {
                        "nodes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "tool": {"type": "string"},
                                    "note": {"type": "string"},
                                    "params_hint": {"type": "object"},
                                },
                            },
                        },
                        "edges": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string"},
                                    "to": {"type": "string"},
                                    "condition": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "summary": {"type": "string", "description": "Short result summary"},
                "satisfaction": {"type": "number", "description": "Satisfaction score 0-1", "default": 0.85},
                "success": {"type": "boolean", "description": "Whether the execution succeeded (default true). Set false to save a failure case as anti-pattern.", "default": True},
                "error_reason": {"type": "string", "description": "Why it failed (only when success=false). E.g. 'API rate limit hit at step 3'"},
            },
            "required": ["request", "graph"],
        },
    },
    "chaeshin_stats": {
        "handler": handle_stats,
        "description": "Get Chaeshin memory store statistics.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "chaeshin_anticipate": {
        "handler": handle_anticipate,
        "description": "Get proactive suggestions based on current context. Chaeshin checks if it has seen a similar situation before.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Current task context or user intent"},
                "category": {"type": "string", "description": "Task category hint"},
            },
            "required": ["context"],
        },
    },
}


def _send(msg: dict):
    """JSON-RPC 메시지 전송."""
    data = json.dumps(msg)
    sys.stdout.write(f"Content-Length: {len(data.encode())}\r\n\r\n{data}")
    sys.stdout.flush()


def _read() -> dict | None:
    """JSON-RPC 메시지 수신. EOF이면 None 반환."""
    # Content-Length 헤더 읽기
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            return None  # EOF — 연결 끊김
        if line.strip() == "":
            break
        if ":" in line:
            key, val = line.split(":", 1)
            headers[key.strip()] = val.strip()

    content_length = int(headers.get("Content-Length", 0))
    if content_length == 0:
        return {}  # 빈 메시지 — 무시하되 서버는 유지

    body = sys.stdin.read(content_length)
    if not body:
        return None
    return json.loads(body)


def run_server():
    """MCP stdio 서버 메인 루프."""
    while True:
        try:
            msg = _read()
        except (EOFError, KeyboardInterrupt):
            break
        except Exception:
            continue  # 파싱 에러 등 — 무시하고 다음 메시지 대기

        if msg is None:
            break  # EOF — 연결 끊김

        if not msg:
            continue  # 빈 메시지 — 서버 유지

        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "initialize":
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "chaeshin",
                        "version": "0.1.0",
                    },
                },
            })

        elif method == "notifications/initialized":
            pass  # 확인만

        elif method == "tools/list":
            tool_list = []
            for name, spec in TOOLS.items():
                tool_list.append({
                    "name": name,
                    "description": spec["description"],
                    "inputSchema": spec["inputSchema"],
                })
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": tool_list},
            })

        elif method == "tools/call":
            tool_name = msg.get("params", {}).get("name", "")
            arguments = msg.get("params", {}).get("arguments", {})

            if tool_name in TOOLS:
                try:
                    result = TOOLS[tool_name]["handler"](arguments)
                    _send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                        },
                    })
                except Exception as e:
                    _send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                            "isError": True,
                        },
                    })
            else:
                _send({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}",
                    },
                })

        elif method == "ping":
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {}})


def main():
    run_server()


if __name__ == "__main__":
    main()
