"""SQLite 백엔드 테스트 — 저장/로드/이벤트/계층."""

from __future__ import annotations

from pathlib import Path

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
from chaeshin.storage.sqlite_backend import SQLiteBackend


def _case(request: str, layer: str = "L1", success: bool = True) -> Case:
    return Case(
        problem_features=ProblemFeatures(
            request=request,
            category="test",
            keywords=[request],
        ),
        solution=Solution(
            tool_graph=ToolGraph(
                nodes=[GraphNode(id="n1", tool="Bash", note=request)],
                edges=[],
            ),
        ),
        outcome=Outcome(success=success, user_satisfaction=0.9 if success else 0.0),
        metadata=CaseMetadata(source="test", layer=layer),
    )


class TestUpsertAndLoad:
    def test_round_trip(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "chaeshin.db")
        case = _case("deploy to staging", layer="L2")
        backend.upsert_case(case, embedding=[0.1, 0.2, 0.3])

        loaded = backend.load_all_cases()
        embeddings = backend.load_embeddings()

        assert len(loaded) == 1
        assert loaded[0].metadata.case_id == case.metadata.case_id
        assert loaded[0].metadata.layer == "L2"
        assert embeddings[case.metadata.case_id] == [0.1, 0.2, 0.3]

    def test_upsert_updates_existing(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "chaeshin.db")
        case = _case("build")
        backend.upsert_case(case)

        case.problem_features.request = "build v2"
        backend.upsert_case(case)

        loaded = backend.load_all_cases()
        assert len(loaded) == 1
        assert loaded[0].problem_features.request == "build v2"


class TestHierarchy:
    def test_link_and_query(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "chaeshin.db")
        parent = _case("strategy", layer="L3")
        child = _case("workflow", layer="L2")
        backend.upsert_case(parent)
        backend.upsert_case(child)

        backend.link(parent.metadata.case_id, child.metadata.case_id, "n1")

        edges = backend.hierarchy_edges()
        assert len(edges) == 1
        assert edges[0]["parent_case_id"] == parent.metadata.case_id
        assert edges[0]["child_case_id"] == child.metadata.case_id
        assert edges[0]["parent_node_id"] == "n1"

    def test_link_is_idempotent(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "chaeshin.db")
        p = _case("p", layer="L3")
        c = _case("c", layer="L2")
        backend.upsert_case(p)
        backend.upsert_case(c)

        backend.link(p.metadata.case_id, c.metadata.case_id)
        backend.link(p.metadata.case_id, c.metadata.case_id)

        assert len(backend.hierarchy_edges()) == 1


class TestEvents:
    def test_append_and_query(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "chaeshin.db")
        backend.append_event("retrieve", {"query": "deploy", "scores": [0.9, 0.7]})
        backend.append_event("retain", {"case_id": "abc"}, case_ids=["abc"])

        assert backend.event_count() == 2
        events = backend.recent_events(limit=10)
        # ORDER BY id DESC
        assert events[0]["event_type"] == "retain"
        assert events[0]["case_ids"] == ["abc"]
        assert events[1]["event_type"] == "retrieve"
        assert events[1]["payload"]["query"] == "deploy"

    def test_filter_by_type(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "chaeshin.db")
        backend.append_event("retrieve", {})
        backend.append_event("retain", {})
        backend.append_event("retrieve", {})

        only_retrieve = backend.recent_events(event_type="retrieve")
        assert len(only_retrieve) == 2
        assert all(e["event_type"] == "retrieve" for e in only_retrieve)


class TestCaseStoreBackendIntegration:
    def test_retain_persists(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "chaeshin.db")
        store = CaseStore(backend=backend, auto_load=False)
        store.retain(_case("foo"))
        store.retain(_case("bar"))

        # 새 스토어를 띄워도 DB에서 복원되어야 함
        store2 = CaseStore(backend=backend, auto_load=True)
        requests = sorted(c.problem_features.request for c in store2.cases)
        assert requests == ["bar", "foo"]

    def test_link_parent_child_persists(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "chaeshin.db")
        store = CaseStore(backend=backend, auto_load=False)
        parent = _case("plan", layer="L3")
        child = _case("step", layer="L2")
        store.retain(parent)
        store.retain(child)

        store.link_parent_child(parent.metadata.case_id, child.metadata.case_id, "n1")

        store2 = CaseStore(backend=backend, auto_load=True)
        reloaded_parent = store2.get_case_by_id(parent.metadata.case_id)
        reloaded_child = store2.get_case_by_id(child.metadata.case_id)
        assert child.metadata.case_id in reloaded_parent.metadata.child_case_ids
        assert reloaded_child.metadata.parent_case_id == parent.metadata.case_id
