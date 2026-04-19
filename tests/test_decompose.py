"""chaeshin_decompose 위임 프로토콜 테스트.

호스트 AI가 decompose 결과를 받아 retain을 L3→L2→L1 순으로 호출하는
시나리오를 mock으로 검증.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chaeshin.case_store import CaseStore
from chaeshin.schema import (
    Case,
    CaseMetadata,
    GraphNode,
    Outcome,
    ProblemFeatures,
    Solution,
    ToolGraph,
)
from chaeshin.storage.sqlite_backend import SQLiteBackend


@pytest.fixture
def isolated_mcp(tmp_path: Path, monkeypatch):
    """mcp_server의 전역 backend/DB를 tmp_path로 리다이렉트."""
    import chaeshin.integrations.claude_code.mcp_server as srv

    test_db = tmp_path / "chaeshin.db"
    test_backend = SQLiteBackend(test_db)
    monkeypatch.setattr(srv, "_backend", test_backend)
    monkeypatch.setattr(srv, "DB_PATH", test_db)
    # event log 도 테스트 backend 사용
    from chaeshin.event_log import EventLog
    monkeypatch.setattr(srv, "_event_log", EventLog(test_backend))
    return srv


class TestDecomposeContract:
    def test_returns_schema_and_protocol(self, isolated_mcp):
        srv = isolated_mcp
        raw = srv.chaeshin_decompose(
            query="deploy to staging after legal review",
            tools="Bash,Read,Edit",
        )
        payload = json.loads(raw)

        assert "layer_schema" in payload
        ls = payload["layer_schema"]
        assert ls.get("recursive") is True
        assert "leaf" in ls and "composite" in ls

        assert "retain_protocol" in payload
        proto = payload["retain_protocol"]
        assert proto["style"] == "recursive_tree"
        assert "leaf_rule" in proto
        assert "verdict_rule" in proto
        # 예시는 재귀 분해 + verdict까지 4단계
        assert len(proto["example_sequence"]) >= 3

        assert payload["available_tools"] == ["Bash", "Read", "Edit"]
        assert "next_action" in payload


class TestHostDrivenDecomposition:
    def test_retain_tree_l3_l2_l1(self, isolated_mcp):
        """호스트 AI가 decompose 응답을 받아 L3→L2→L1 트리를 저장하는 시나리오."""
        srv = isolated_mcp

        l3_raw = srv.chaeshin_retain(
            request="production hotfix rollout",
            graph={
                "nodes": [
                    {"id": "s1", "tool": "plan", "note": "assess blast radius"},
                    {"id": "s2", "tool": "plan", "note": "deploy + verify"},
                ],
                "edges": [{"from": "s1", "to": "s2"}],
            },
            category="strategy",
            layer="L3",
        )
        l3_id = json.loads(l3_raw)["case_id"]

        l2_raw = srv.chaeshin_retain(
            request="deploy + verify",
            graph={
                "nodes": [
                    {"id": "w1", "tool": "Bash", "note": "build"},
                    {"id": "w2", "tool": "Bash", "note": "deploy"},
                ],
                "edges": [{"from": "w1", "to": "w2"}],
            },
            category="workflow",
            layer="L2",
            parent_case_id=l3_id,
            parent_node_id="s2",
        )
        l2_id = json.loads(l2_raw)["case_id"]

        l1_raw = srv.chaeshin_retain(
            request="kubectl rollout",
            graph={"nodes": [{"id": "n1", "tool": "Bash", "note": "kubectl rollout status"}]},
            category="atomic",
            layer="L1",
            parent_case_id=l2_id,
            parent_node_id="w2",
        )
        l1_id = json.loads(l1_raw)["case_id"]

        # 재조회
        store = CaseStore(backend=srv._backend, auto_load=True)
        l3_case = store.get_case_by_id(l3_id)
        l2_case = store.get_case_by_id(l2_id)
        l1_case = store.get_case_by_id(l1_id)

        assert l3_case.metadata.layer == "L3"
        assert l2_id in l3_case.metadata.child_case_ids
        assert l2_case.metadata.parent_case_id == l3_id
        assert l1_id in l2_case.metadata.child_case_ids
        assert l1_case.metadata.parent_case_id == l2_id
        assert l1_case.metadata.parent_node_id == "w2"

        # retain은 pending으로 저장됨 — verdict를 성공으로 기록해야 successes에 노출.
        srv.chaeshin_verdict(case_id=l3_id, status="success", note="ok")
        srv.chaeshin_verdict(case_id=l2_id, status="success", note="ok")
        srv.chaeshin_verdict(case_id=l1_id, status="success", note="ok")

        retrieve_raw = srv.chaeshin_retrieve(
            query="production hotfix rollout",
            include_children=True,
            min_similarity=0.0,
        )
        payload = json.loads(retrieve_raw)
        assert "successes" in payload
        root = next(c for c in payload["successes"] if c["case_id"] == l3_id)
        assert root["layer"] == "L3"
        assert root["outcome"]["status"] == "success"
        assert root["children"]
        l2_node = next(c for c in root["children"] if c["case_id"] == l2_id)
        assert l2_node["layer"] == "L2"
        assert l2_node["children"]
        assert l2_node["children"][0]["layer"] == "L1"

    def test_retain_defaults_to_pending(self, isolated_mcp):
        """chaeshin_retain은 outcome=pending + deadline_at 설정."""
        srv = isolated_mcp
        raw = srv.chaeshin_retain(
            request="set up CI",
            graph={"nodes": [{"id": "n1", "tool": "Bash"}]},
            layer="L1",
        )
        payload = json.loads(raw)
        assert payload["outcome_status"] == "pending"
        assert payload["wait_mode"] == "deadline"
        assert payload["deadline_at"]  # 기본 deadline 설정됨

    def test_verdict_transitions_pending_to_success(self, isolated_mcp):
        srv = isolated_mcp
        retained = json.loads(srv.chaeshin_retain(
            request="ship feature X",
            graph={"nodes": [{"id": "n1", "tool": "Edit"}]},
        ))
        cid = retained["case_id"]

        verdict = json.loads(srv.chaeshin_verdict(
            case_id=cid, status="success", note="완벽해",
        ))
        assert verdict["outcome_status"] == "success"

        # 재조회 시 successes에 등장
        from chaeshin.case_store import CaseStore
        store = CaseStore(backend=srv._backend, auto_load=True)
        case = store.get_case_by_id(cid)
        assert case.outcome.status == "success"
        assert case.outcome.verdict_note == "완벽해"
        assert case.outcome.verdict_at

    def test_update_applies_diff(self, isolated_mcp):
        srv = isolated_mcp
        retained = json.loads(srv.chaeshin_retain(
            request="original",
            graph={"nodes": [{"id": "n1", "tool": "Read"}]},
            category="init",
        ))
        cid = retained["case_id"]

        updated = json.loads(srv.chaeshin_update(
            case_id=cid,
            patch={
                "problem_features": {"request": "updated request"},
                "metadata": {"layer": "L2"},
            },
        ))
        assert set(updated["changed_fields"]) >= {
            "problem_features.request",
            "metadata.layer",
        }

        from chaeshin.case_store import CaseStore
        store = CaseStore(backend=srv._backend, auto_load=True)
        case = store.get_case_by_id(cid)
        assert case.problem_features.request == "updated request"
        assert case.metadata.layer == "L2"

    def test_delete_removes_case(self, isolated_mcp):
        srv = isolated_mcp
        retained = json.loads(srv.chaeshin_retain(
            request="to delete",
            graph={"nodes": [{"id": "n1", "tool": "Bash"}]},
        ))
        cid = retained["case_id"]

        result = json.loads(srv.chaeshin_delete(case_id=cid, reason="test"))
        assert result["status"] == "deleted"

        from chaeshin.case_store import CaseStore
        store = CaseStore(backend=srv._backend, auto_load=True)
        assert store.get_case_by_id(cid) is None

    def test_events_recorded(self, isolated_mcp):
        srv = isolated_mcp
        srv.chaeshin_decompose(query="x", tools="")
        retained = json.loads(srv.chaeshin_retain(
            request="x step",
            graph={"nodes": [{"id": "n1", "tool": "Read"}]},
            layer="L1",
        ))
        cid = retained["case_id"]
        srv.chaeshin_retrieve(query="x", min_similarity=0.0)
        srv.chaeshin_update(case_id=cid, patch={"metadata": {"layer": "L2"}})
        srv.chaeshin_verdict(case_id=cid, status="success", note="good")
        srv.chaeshin_delete(case_id=cid)

        events = srv._backend.recent_events(limit=50)
        types = [e["event_type"] for e in events]
        for expected in ("decompose_context", "retain", "retrieve", "update", "verdict", "delete"):
            assert expected in types, f"{expected} missing from {types}"
