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

        # 루트부터 retain — layer/depth 는 안 넘김 (derived)
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
            parent_case_id=l3_id,
            parent_node_id="s2",
        )
        l2_id = json.loads(l2_raw)["case_id"]

        l1_raw = srv.chaeshin_retain(
            request="kubectl rollout",
            graph={"nodes": [{"id": "n1", "tool": "Bash", "note": "kubectl rollout status"}]},
            category="atomic",
            parent_case_id=l2_id,
            parent_node_id="w2",
        )
        l1_id = json.loads(l1_raw)["case_id"]

        # 재조회 — layer 는 derived. 트리 깊이로 자동 계산.
        store = CaseStore(backend=srv._backend, auto_load=True)
        l3_case = store.get_case_by_id(l3_id)
        l2_case = store.get_case_by_id(l2_id)
        l1_case = store.get_case_by_id(l1_id)

        assert store.derive_layer(l3_id) == "L3"
        assert store.derive_layer(l2_id) == "L2"
        assert store.derive_layer(l1_id) == "L1"
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
        )
        payload = json.loads(raw)
        assert payload["outcome_status"] == "pending"
        assert payload["wait_mode"] == "deadline"
        assert payload["deadline_at"]  # 기본 deadline 설정됨
        assert payload["layer"] == "L1"  # 자식 없음 → derived L1

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
                "metadata": {"difficulty": 2},
            },
        ))
        assert set(updated["changed_fields"]) >= {
            "problem_features.request",
            "metadata.difficulty",
        }

        from chaeshin.case_store import CaseStore
        store = CaseStore(backend=srv._backend, auto_load=True)
        case = store.get_case_by_id(cid)
        assert case.problem_features.request == "updated request"
        assert case.metadata.difficulty == 2

    def test_revise_cascades_to_orphan_children(self, isolated_mcp):
        """상위 그래프에서 노드를 제거하면, 그 노드를 parent_node_id로 가진 자식은 pending으로 되돌림."""
        srv = isolated_mcp

        # 루트 그래프: s1 → s2 → s3 (세 노드). layer 는 자식 붙은 후 derived L2.
        l3 = json.loads(srv.chaeshin_retain(
            request="multi-step strategy",
            graph={
                "nodes": [
                    {"id": "s1", "tool": "compose", "note": "plan"},
                    {"id": "s2", "tool": "compose", "note": "execute"},
                    {"id": "s3", "tool": "compose", "note": "followup"},
                ],
                "edges": [
                    {"from": "s1", "to": "s2"},
                    {"from": "s2", "to": "s3"},
                ],
            },
        ))
        l3_id = l3["case_id"]

        # s2 노드에 매달린 자식, s3 노드에 매달린 자식
        l2_a = json.loads(srv.chaeshin_retain(
            request="execute workflow",
            graph={"nodes": [{"id": "n1", "tool": "Bash"}]},
            parent_case_id=l3_id,
            parent_node_id="s2",
        ))
        l2_b = json.loads(srv.chaeshin_retain(
            request="followup workflow",
            graph={"nodes": [{"id": "n1", "tool": "Read"}]},
            parent_case_id=l3_id,
            parent_node_id="s3",
        ))
        # 자식들에 verdict=success까지 먼저 줘서 pending이 아니게 한다
        srv.chaeshin_verdict(case_id=l2_a["case_id"], status="success")
        srv.chaeshin_verdict(case_id=l2_b["case_id"], status="success")

        # L3 그래프 수정 — s3 제거, s4 추가
        revised = json.loads(srv.chaeshin_revise(
            case_id=l3_id,
            graph={
                "nodes": [
                    {"id": "s1", "tool": "compose"},
                    {"id": "s2", "tool": "compose"},
                    {"id": "s4", "tool": "compose", "note": "new step"},
                ],
                "edges": [
                    {"from": "s1", "to": "s2"},
                    {"from": "s2", "to": "s4"},
                ],
            },
            reason="s3 was unnecessary, replaced with s4",
        ))

        assert revised["removed_nodes"] == ["s3"]
        assert "s4" in revised["added_nodes"]
        assert l2_b["case_id"] in revised["orphaned_children"]  # s3 매달린 자식 고아화
        assert l2_a["case_id"] not in revised["orphaned_children"]  # s2 그대로

        # 재조회해서 상태 확인
        from chaeshin.case_store import CaseStore
        store = CaseStore(backend=srv._backend, auto_load=True)
        orphan = store.get_case_by_id(l2_b["case_id"])
        survivor = store.get_case_by_id(l2_a["case_id"])
        assert orphan.outcome.status == "pending"  # pending으로 되돌림
        assert any("cascade" in line for line in orphan.metadata.feedback_log)
        assert survivor.outcome.status == "success"  # 영향 없음

    def test_revise_without_cascade_preserves_children(self, isolated_mcp):
        srv = isolated_mcp
        parent = json.loads(srv.chaeshin_retain(
            request="p",
            graph={"nodes": [{"id": "a", "tool": "t"}]},
        ))
        child = json.loads(srv.chaeshin_retain(
            request="c",
            graph={"nodes": [{"id": "n1", "tool": "t"}]},
            parent_case_id=parent["case_id"],
            parent_node_id="a",
        ))
        srv.chaeshin_verdict(case_id=child["case_id"], status="success")

        result = json.loads(srv.chaeshin_revise(
            case_id=parent["case_id"],
            graph={"nodes": [{"id": "b", "tool": "t"}]},  # 'a' 제거됨
            cascade=False,
        ))
        assert result["removed_nodes"] == ["a"]
        assert result["orphaned_children"] == []  # cascade=False이므로 자식 그대로

        from chaeshin.case_store import CaseStore
        store = CaseStore(backend=srv._backend, auto_load=True)
        kept = store.get_case_by_id(child["case_id"])
        assert kept.outcome.status == "success"

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
        ))
        cid = retained["case_id"]
        srv.chaeshin_retrieve(query="x", min_similarity=0.0)
        srv.chaeshin_update(case_id=cid, patch={"metadata": {"difficulty": 1}})
        srv.chaeshin_revise(
            case_id=cid,
            graph={"nodes": [{"id": "n2", "tool": "Edit"}]},
            reason="swap tool",
        )
        srv.chaeshin_verdict(case_id=cid, status="success", note="good")
        srv.chaeshin_delete(case_id=cid)

        events = srv._backend.recent_events(limit=50)
        types = [e["event_type"] for e in events]
        for expected in (
            "decompose_context", "retain", "retrieve",
            "update", "revise", "verdict", "delete",
        ):
            assert expected in types, f"{expected} missing from {types}"
