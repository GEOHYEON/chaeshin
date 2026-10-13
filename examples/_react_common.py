"""예시 공용 헬퍼 — Chaeshin 도구들을 ReAct 에이전트에 붙이는 어댑터.

각 도메인 데모(`cooking`, `medical_intake`, `lifestyle_coaching`)가 공통으로 쓴다.
OPENAI_API_KEY 확인, CaseStore+EventLog 초기화, Chaeshin ToolSpec 묶음 반환까지.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import uuid
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
from chaeshin.search import normalize_keywords
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


def build_adapter(model: str = "gpt-6-luna"):
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


def build_store(
    session_id: str,
    *,
    embed_fn=None,
) -> Tuple[CaseStore, EventLog, "tempfile.TemporaryDirectory"]:
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
        store = CaseStore(embed_fn=embed_fn, backend=backend, auto_load=True)
        return store, events, tmp

    tmp = tempfile.TemporaryDirectory()
    db_path = Path(tmp.name) / "react-demo.db"
    backend = SQLiteBackend(db_path)
    events = EventLog(backend, session_id=session_id)
    store = CaseStore(embed_fn=embed_fn, backend=backend, auto_load=False)
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
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "query is required"}

        context_arg = args.get("context") or {}
        if not isinstance(context_arg, dict):
            return {"error": "context must be an object"}
        context = dict(context_arg)

        intent = str(args.get("intent", context.get("intent", ""))).strip()
        goal = str(args.get("goal", context.get("goal", ""))).strip()
        entities = args.get("entities", context.get("entities", {}))
        current_state = args.get("current_state", context.get("current_state", {}))
        blocking_unknowns = _as_list(
            args.get("blocking_unknowns", context.get("blocking_unknowns", []))
        )
        optional_unknowns = _as_list(
            args.get("optional_unknowns", context.get("optional_unknowns", []))
        )

        if intent:
            context["intent"] = intent
        if goal:
            context["goal"] = goal
        if entities:
            context["entities"] = entities
        if current_state:
            context["current_state"] = current_state
        # unknown은 관찰된 사실이 아니므로 검색용 context에 섞지 않는다.
        # Observation의 query_profile에는 따로 보존해 ReAct가 질문/관찰 여부를 판단한다.

        kw_list = normalize_keywords(args.get("keywords"))
        constraints = _as_list(args.get("constraints"))
        request_category = str(args.get("category") or category).strip()
        probe = ProblemFeatures(
            request=query,
            category=request_category,
            keywords=kw_list,
            constraints=constraints,
            context=context,
        )
        top_k = _as_int(args.get("top_k", 5), default=5, minimum=1)
        top_k_failures = _as_int(
            args.get("top_k_failures", 3), default=3, minimum=0
        )
        result = store.retrieve_with_warnings(
            probe,
            top_k=top_k,
            top_k_failures=top_k_failures,
        )

        state_revision = _as_int(args.get("state_revision", 0), default=0, minimum=0)
        query_profile = {
            "query": query,
            "category": request_category,
            "keywords": kw_list,
            "intent": intent,
            "goal": goal,
            "constraints": constraints,
            "context": context,
            "blocking_unknowns": blocking_unknowns,
            "optional_unknowns": optional_unknowns,
            "state_revision": state_revision,
            "reason": str(args.get("reason", "initial")),
            "changed_fields": _as_list(args.get("changed_fields")),
            "previous_retrieval_id": args.get("previous_retrieval_id"),
        }
        state_fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "query": query,
                    "constraints": constraints,
                    "context": context,
                    "blocking_unknowns": blocking_unknowns,
                    "optional_unknowns": optional_unknowns,
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()[:16]
        retrieval_id = f"ret-{uuid.uuid4().hex[:12]}"

        successes = [_case_evidence(c, s, store) for c, s in result["cases"]]
        warnings = [_case_evidence(c, s, store) for c, s in result["warnings"]]
        pending = [
            _case_evidence(c, s, store) for c, s in result.get("pending", [])
        ]
        all_returned = successes + warnings + pending
        returned_ids = {item["case_id"] for item in all_returned}
        candidates = [
            case for case in store.cases
            if getattr(case.metadata, "is_head", True)
        ]
        embedded_ids = getattr(store, "_embeddings", {})
        search_mode = getattr(
            store,
            "last_retrieval_mode",
            "hybrid" if store.embed_fn else "lexical",
        )
        if search_mode == "uninitialized":
            search_mode = "hybrid" if store.embed_fn else "lexical"

        payload = {
            "kind": "chaeshin.memory_observation",
            "schema_version": "1.0",
            "retrieval_id": retrieval_id,
            "state_revision": state_revision,
            "state_fingerprint": state_fingerprint,
            "contract": {
                "role": "procedural_reference_not_plan",
                "instruction": (
                    "Use this evidence as reference when choosing the next Action; "
                    "do not execute a graph merely because it ranks first."
                ),
            },
            "query_profile": query_profile,
            "retrieval": {
                "mode": search_mode,
                "ranking": (
                    "dense(0.6)+lexical(0.3)+quality(0.1)"
                    if search_mode == "hybrid"
                    else "lexical(0.8)+quality(0.2)"
                ),
                "embedding_coverage": {
                    "embedded_cases": sum(
                        1 for case in candidates
                        if case.metadata.case_id in embedded_ids
                    ),
                    "candidate_cases": len(candidates),
                },
            },
            "successes": successes,
            "warnings": warnings,
            "pending": pending,
            "coverage": {
                "total_cases": len(candidates),
                "returned_successes": len(successes),
                "returned_warnings": len(warnings),
                "returned_pending": len(pending),
                "omitted": max(0, len(candidates) - len(returned_ids)),
            },
            "total_in_store": len(store.cases),
        }
        events.record(
            "retrieve",
            {
                "query": query,
                "retrieval_id": retrieval_id,
                "state_revision": state_revision,
                "search_mode": search_mode,
                "n_successes": len(payload["successes"]),
                "n_warnings": len(payload["warnings"]),
            },
            case_ids=sorted(returned_ids),
        )
        return payload

    def _retain(args: Dict[str, Any]) -> Dict[str, Any]:
        request = str(args.get("request", "")).strip()
        graph_dict = args.get("graph") or {}
        if not request:
            return {"error": "request is required"}

        nodes = [
            GraphNode(
                id=n.get("id") or f"n{i}",
                tool=n.get("tool", "unknown"),
                params_hint=n.get("params_hint", {}),
                note=n.get("note", ""),
                input_schema=n.get("input_schema", {}),
                output_schema=n.get("output_schema", {}),
            )
            for i, n in enumerate(graph_dict.get("nodes", []))
        ]
        edges = [
            GraphEdge(
                from_node=e.get("from_node", e.get("from", "")),
                to_node=e.get("to_node", e.get("to")),
                condition=e.get("condition"),
                action=e.get("action"),
                priority=_as_int(e.get("priority", 0), default=0),
                note=e.get("note", ""),
            )
            for e in graph_dict.get("edges", [])
        ]
        kw_list = normalize_keywords(args.get("keywords"))
        constraints = _as_list(args.get("constraints"))
        context = args.get("context") or {}
        if not isinstance(context, dict):
            return {"error": "context must be an object"}
        context = dict(context)
        if args.get("intent"):
            context["intent"] = args["intent"]
        deadline_at = ""
        ds = _as_int(args.get("deadline_seconds", 0), default=0, minimum=0)
        if ds > 0:
            deadline_at = (datetime.now() + timedelta(seconds=ds)).isoformat()

        entry_nodes = _as_list(graph_dict.get("entry_nodes"))
        if not entry_nodes and nodes:
            entry_nodes = [nodes[0].id]

        case = Case(
            problem_features=ProblemFeatures(
                request=request,
                category=args.get("category", category),
                keywords=kw_list,
                constraints=constraints,
                context=context,
            ),
            solution=Solution(tool_graph=ToolGraph(
                nodes=nodes,
                edges=edges,
                parallel_groups=graph_dict.get("parallel_groups", []),
                entry_nodes=entry_nodes,
                max_loops=_as_int(graph_dict.get("max_loops", 0), default=0, minimum=0),
            )),
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
            description=(
                "구조화 검색 프로파일로 과거 절차 근거를 hybrid 검색한다. "
                "전체 ProblemFeatures/ToolGraph/outcome을 successes, warnings, pending으로 "
                "반환하지만 계획은 만들지 않는다. 최초 작업과 중요한 상태 변화 뒤 호출."
            ),
            example_input=(
                f'{{"query":"김치찌개 끓이는 법 알려줘","category":"{category}",'
                '"keywords":["김치찌개","조리법"],"intent":"procedure_explanation",'
                '"constraints":[],"context":{"current_state":{"task_mode":"information_only"}},'
                '"blocking_unknowns":[],"optional_unknowns":["servings"],'
                '"state_revision":0,"reason":"initial","top_k":5}'
            ),
            fn=_retrieve,
        ),
        "chaeshin_retain": ToolSpec(
            name="chaeshin_retain",
            description=(
                "실제로 호출한 도메인 도구 trace만 ToolGraph로 저장한다. "
                "호출별 node.tool/params_hint와 실제 순서 edge가 정확해야 하며 결과는 pending. "
                "정보만 설명하고 도메인 도구를 실행하지 않았다면 호출하지 않는다."
            ),
            example_input=(
                '{"request":"김치찌개 2인분 만들어줘","category":"cooking",'
                '"keywords":["김치찌개"],"context":{"retrieval_id":"ret-...",'
                '"selected_case_ids":["recipe_kimchi_stew_001"],"state_revision":0},'
                '"graph":{"entry_nodes":["n1"],'
                '"nodes":[{"id":"n1","tool":"check_fridge","params_hint":{}}],'
                '"edges":[],"parallel_groups":[],"max_loops":0}}'
            ),
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


def _case_evidence(case: Case, score: float, store: CaseStore) -> Dict[str, Any]:
    """ReAct가 다음 Tool을 고를 때 참고할 Case 근거 전체를 직렬화한다."""
    meta = case.metadata
    graph = case.solution.tool_graph
    problem = case.problem_features
    outcome = case.outcome
    return {
        "case_id": meta.case_id,
        "similarity": round(float(score), 4),
        "score": {"final": round(float(score), 4)},
        "usage": "reference_for_next_action",
        "layer": store.derive_layer(meta.case_id),
        "depth": store.derive_depth(meta.case_id),
        "status": outcome.status,
        "problem_features": {
            "request": problem.request,
            "category": problem.category,
            "keywords": list(problem.keywords),
            "constraints": list(problem.constraints),
            "context": problem.context,
        },
        "graph": {
            "nodes": [
                {
                    "id": n.id,
                    "tool": n.tool,
                    "params_hint": n.params_hint,
                    "note": n.note,
                    "input_schema": n.input_schema,
                    "output_schema": n.output_schema,
                }
                for n in graph.nodes
            ],
            "edges": [
                {
                    "from_node": edge.from_node,
                    "to_node": edge.to_node,
                    "condition": edge.condition,
                    "action": edge.action,
                    "priority": edge.priority,
                    "note": edge.note,
                }
                for edge in graph.edges
            ],
            "parallel_groups": graph.parallel_groups,
            "entry_nodes": graph.entry_nodes,
            "max_loops": graph.max_loops,
        },
        "outcome": {
            "status": outcome.status,
            "result_summary": outcome.result_summary,
            "tools_executed": outcome.tools_executed,
            "loops_triggered": outcome.loops_triggered,
            "user_satisfaction": outcome.user_satisfaction,
            "error_reason": outcome.error_reason,
            "verdict_note": outcome.verdict_note,
            "details": outcome.details,
        },
        "provenance": {
            "source": meta.source,
            "version": meta.version,
            "root_case_id": getattr(meta, "root_case_id", "") or meta.case_id,
            "revision_index": getattr(meta, "revision_index", 0),
            "updated_at": meta.updated_at,
            "used_count": meta.used_count,
            "avg_satisfaction": meta.avg_satisfaction,
            "feedback_count": getattr(meta, "feedback_count", 0),
            "tags": getattr(meta, "tags", {}),
        },
    }


def _as_list(value: Any) -> List[str]:
    """문자열/배열 입력을 중복 없는 문자열 목록으로 정규화한다."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = [value]

    result: List[str] = []
    seen = set()
    for item in raw:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _as_int(value: Any, *, default: int, minimum: Optional[int] = None) -> int:
    """도구 JSON의 정수 필드를 안전하게 파싱하고 선택적 하한을 적용한다."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


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
    print("  → 이번 실행에서 새로 retain한 케이스만 pending이며, verdict는 사용자가 전환.")
