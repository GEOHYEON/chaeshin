"""예시 공용 헬퍼 — Chaeshin 도구들을 ReAct 에이전트에 붙이는 어댑터.

각 도메인 데모(`cooking`, `medical_intake`, `lifestyle_coaching`)가 공통으로 쓴다.
OPENAI_API_KEY 확인, CaseStore+EventLog 초기화, Chaeshin ToolSpec 묶음 반환까지.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from chaeshin.agents.react_agent import ToolSpec
from chaeshin.case_store import CaseStore
from chaeshin.event_log import EventLog
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
from chaeshin.storage.sqlite_backend import SQLiteBackend


# ─────────────────────────────────────────────────────────────────────
# 환경 준비
# ─────────────────────────────────────────────────────────────────────


def ensure_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        sys.stderr.write(
            "\n[ERROR] OPENAI_API_KEY 가 없습니다.\n"
            "  다음 중 하나로 설정하세요:\n"
            "    export OPENAI_API_KEY=sk-...\n"
            "    또는 .env 파일에 OPENAI_API_KEY=sk-... 추가\n\n"
        )
        sys.exit(1)
    return key


def build_adapter(model: str = "gpt-4o-mini"):
    """OpenAIAdapter 인스턴스 반환. openai 패키지가 없으면 안내 후 종료."""
    ensure_openai_key()
    try:
        from chaeshin.integrations.openai import OpenAIAdapter
    except ImportError:
        sys.stderr.write(
            "[ERROR] openai 패키지가 없습니다. 설치:\n"
            "  uv pip install 'openai>=1.0'\n"
        )
        sys.exit(1)
    return OpenAIAdapter(model=model, temperature=0.1)


def build_store(session_id: str) -> Tuple[CaseStore, EventLog, "tempfile.TemporaryDirectory"]:
    """임시 디렉터리에 SQLite 저장소를 만들어 반환.

    데모 종료 시 `tmp.cleanup()`을 호출하면 데이터가 사라진다.
    적재된 케이스를 진짜 홈 DB에 넣고 싶으면 CHAESHIN_DEMO_PERSIST=1 로 설정.
    """
    persist = os.getenv("CHAESHIN_DEMO_PERSIST", "").lower() in ("1", "true", "yes")
    if persist:
        db_path = Path(os.path.expanduser("~/.chaeshin/chaeshin.db"))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.TemporaryDirectory()  # dummy — not used
        backend = SQLiteBackend(db_path)
        events = EventLog(backend, session_id=session_id)
        store = CaseStore(backend=backend, auto_load=True)
        return store, events, tmp

    tmp = tempfile.TemporaryDirectory()
    db_path = Path(tmp.name) / "react-demo.db"
    backend = SQLiteBackend(db_path)
    events = EventLog(backend, session_id=session_id)
    store = CaseStore(backend=backend, auto_load=False)
    return store, events, tmp


# ─────────────────────────────────────────────────────────────────────
# Chaeshin Tools (ReAct ToolSpec으로 래핑)
# ─────────────────────────────────────────────────────────────────────


def chaeshin_tools(
    store: CaseStore,
    events: EventLog,
    *,
    category: str = "demo",
    source: str = "react-demo",
) -> Dict[str, ToolSpec]:
    """Chaeshin 도구 4개 + feedback 한 세트를 ToolSpec 딕셔너리로 반환."""

    def _retrieve(args: Dict[str, Any]) -> Dict[str, Any]:
        query = args.get("query", "").strip()
        if not query:
            return {"error": "query is required"}
        keywords = args.get("keywords", "")
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else []
        probe = ProblemFeatures(
            request=query,
            category=args.get("category", category),
            keywords=kw_list,
        )
        result = store.retrieve_with_warnings(
            probe,
            top_k=int(args.get("top_k", 3)),
            top_k_failures=int(args.get("top_k_failures", 2)),
        )
        payload = {
            "successes": [_brief(c, s, store) for c, s in result["cases"]],
            "warnings": [_brief(c, s, store) for c, s in result["warnings"]],
            "pending": [_brief(c, s, store) for c, s in result.get("pending", [])],
            "total_in_store": len(store.cases),
        }
        events.record(
            "retrieve",
            {
                "query": query,
                "n_successes": len(payload["successes"]),
                "n_warnings": len(payload["warnings"]),
            },
            case_ids=[s["case_id"] for s in payload["successes"]],
        )
        return payload

    def _retain(args: Dict[str, Any]) -> Dict[str, Any]:
        request = args.get("request", "").strip()
        graph_dict = args.get("graph") or {}
        if not request:
            return {"error": "request is required"}

        nodes = [
            GraphNode(
                id=n.get("id") or f"n{i}",
                tool=n.get("tool", "unknown"),
                params_hint=n.get("params_hint", {}),
                note=n.get("note", ""),
            )
            for i, n in enumerate(graph_dict.get("nodes", []))
        ]
        edges = [
            GraphEdge(
                from_node=e.get("from_node", e.get("from", "")),
                to_node=e.get("to_node", e.get("to")),
                condition=e.get("condition"),
            )
            for e in graph_dict.get("edges", [])
        ]
        kw = args.get("keywords", "")
        kw_list = [k.strip() for k in kw.split(",") if k.strip()] if kw else []
        deadline_at = ""
        ds = int(args.get("deadline_seconds", 0))
        if ds > 0:
            deadline_at = (datetime.now() + timedelta(seconds=ds)).isoformat()

        case = Case(
            problem_features=ProblemFeatures(
                request=request,
                category=args.get("category", category),
                keywords=kw_list,
            ),
            solution=Solution(tool_graph=ToolGraph(nodes=nodes, edges=edges)),
            outcome=Outcome(status="pending"),
            metadata=CaseMetadata(
                source=source,
                parent_case_id=args.get("parent_case_id", ""),
                parent_node_id=args.get("parent_node_id", ""),
                wait_mode=args.get("wait_mode", "deadline"),
                deadline_at=deadline_at,
            ),
        )
        case_id = store.retain(case)
        parent = args.get("parent_case_id", "")
        if parent:
            store.link_parent_child(parent, case_id, args.get("parent_node_id", ""))
        derived_layer = store.derive_layer(case_id)
        derived_depth = store.derive_depth(case_id)
        events.record(
            "retain",
            {
                "request": request,
                "layer": derived_layer,
                "depth": derived_depth,
                "parent_case_id": parent,
                "node_count": len(nodes),
            },
            case_ids=[case_id] + ([parent] if parent else []),
        )
        return {
            "case_id": case_id,
            "status": "saved",
            "outcome_status": "pending",
            "layer": derived_layer,
        }

    def _revise(args: Dict[str, Any]) -> Dict[str, Any]:
        case_id = args.get("case_id", "")
        nodes = args.get("nodes") or []
        edges = args.get("edges") or []
        reason = args.get("reason", "")
        cascade = bool(args.get("cascade", True))
        result = store.revise_graph(case_id, nodes=nodes, edges=edges, cascade=cascade, reason=reason)
        if result is None:
            return {"error": f"case not found: {case_id}"}
        events.record(
            "revise",
            {
                "reason": reason,
                "added": result["added_nodes"],
                "removed": result["removed_nodes"],
                "orphaned": result["orphaned_children"],
            },
            case_ids=[case_id] + result["orphaned_children"],
        )
        return result

    def _verdict(args: Dict[str, Any]) -> Dict[str, Any]:
        case_id = args.get("case_id", "")
        status = args.get("status", "")
        note = args.get("note", "")
        if status not in ("success", "failure"):
            return {"error": "status must be 'success' or 'failure'"}
        case = store.set_verdict(case_id, status, note)
        if case is None:
            return {"error": f"case not found: {case_id}"}
        events.record("verdict", {"status": status, "note": note}, case_ids=[case_id])
        return {"case_id": case_id, "outcome_status": status}

    def _feedback(args: Dict[str, Any]) -> Dict[str, Any]:
        case_id = args.get("case_id", "")
        fb = args.get("feedback", "")
        ftype = args.get("feedback_type", "modify")
        updated = store.add_feedback(case_id, fb, ftype)
        if updated is None:
            return {"error": f"case not found: {case_id}"}
        events.record(
            "feedback",
            {"feedback_type": ftype, "feedback_count": updated.metadata.feedback_count},
            case_ids=[case_id],
        )
        return {
            "case_id": case_id,
            "feedback_count": updated.metadata.feedback_count,
        }

    return {
        "chaeshin_retrieve": ToolSpec(
            name="chaeshin_retrieve",
            description="과거 비슷한 케이스 검색. successes / warnings / pending 세 리스트를 돌려준다. 작업 시작 전에 항상 호출.",
            example_input='{"query": "kimchi stew for 2", "keywords": "kimchi,stew", "top_k": 3}',
            fn=_retrieve,
        ),
        "chaeshin_retain": ToolSpec(
            name="chaeshin_retain",
            description="실행한 tool graph를 pending 상태로 저장. 작업을 끝내기 전에 호출. parent_case_id로 계층 연결 (layer 는 derived).",
            example_input='{"request": "kimchi stew for 2", "category": "cooking", "keywords": "kimchi,stew", "graph": {"nodes": [{"id":"n1","tool":"check_fridge"}], "edges": []}}',
            fn=_retain,
        ),
        "chaeshin_revise": ToolSpec(
            name="chaeshin_revise",
            description="이 레이어의 graph를 새로 쓴다. 제거된 노드에 붙어있던 자식 케이스는 pending으로 회귀한다(cascade).",
            example_input='{"case_id": "<id>", "nodes": [{"id":"n1","tool":"..."}], "edges": [], "reason": "왜 바꿨는지"}',
            fn=_revise,
        ),
        "chaeshin_verdict": ToolSpec(
            name="chaeshin_verdict",
            description="사용자의 성공/실패 판정을 기록. 에이전트 스스로 추정해서 호출하지 말고, 사용자가 명시한 경우에만 사용.",
            example_input='{"case_id": "<id>", "status": "success", "note": "사용자 인용"}',
            fn=_verdict,
        ),
        "chaeshin_feedback": ToolSpec(
            name="chaeshin_feedback",
            description="케이스에 자연어 피드백 기록. feedback_count가 오르면 다음 retrieve에서 우선순위 상승.",
            example_input='{"case_id": "<id>", "feedback": "간이 짜다", "feedback_type": "modify"}',
            fn=_feedback,
        ),
    }


def _brief(case: Case, score: float, store: CaseStore) -> Dict[str, Any]:
    meta = case.metadata
    return {
        "case_id": meta.case_id,
        "similarity": round(float(score), 4),
        "request": case.problem_features.request,
        "layer": store.derive_layer(meta.case_id),
        "status": case.outcome.status,
        "graph": {
            "nodes": [
                {"id": n.id, "tool": n.tool, "note": n.note}
                for n in case.solution.tool_graph.nodes[:6]
            ],
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Summary printer
# ─────────────────────────────────────────────────────────────────────


def print_store_summary(store: CaseStore, events: EventLog):
    print("\n\033[36m═══════════════════════════════════════════════\n  저장소 현황\n═══════════════════════════════════════════════\033[0m")
    status_counts: Dict[str, int] = {}
    for c in store.cases:
        status_counts[c.outcome.status] = status_counts.get(c.outcome.status, 0) + 1
    print(f"  케이스: {len(store.cases)}건")
    print(f"  상태별: {status_counts}")
    if store.backend is not None:
        print(f"  이벤트: {store.backend.event_count()}건")
    print("  → 저장된 케이스는 모두 pending. 나중에 사용자가 verdict로 전환.")
