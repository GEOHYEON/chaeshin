"""Seed store 격리 테스트 — seed.db 와 main chaeshin.db 가 독립."""

from __future__ import annotations

from pathlib import Path

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
from chaeshin.seed import default_seed_db_path, open_seed_store
from chaeshin.storage.sqlite_backend import SQLiteBackend


def _case(request: str) -> Case:
    return Case(
        problem_features=ProblemFeatures(request=request, category="test", keywords=[request]),
        solution=Solution(
            tool_graph=ToolGraph(nodes=[GraphNode(id="n1", tool="Bash", note=request)])
        ),
        outcome=Outcome(status="pending"),
        metadata=CaseMetadata(source="seed:test"),
    )


class TestSeedStoreIsolation:
    def test_seed_and_main_dbs_are_separate(self, tmp_path: Path):
        seed_path = tmp_path / "seed.db"
        main_path = tmp_path / "chaeshin.db"

        seed_store = open_seed_store(db_path=str(seed_path))
        main_backend = SQLiteBackend(str(main_path))
        main_store = CaseStore(backend=main_backend, auto_load=True)

        seed_store.retain(_case("seed only"))

        assert len(seed_store.cases) == 1
        assert len(main_store.cases) == 0

        # Reload main fresh — 여전히 비어있어야 함
        main_store_2 = CaseStore(backend=SQLiteBackend(str(main_path)), auto_load=True)
        assert len(main_store_2.cases) == 0

    def test_default_seed_db_path_uses_env_override(self, monkeypatch, tmp_path: Path):
        custom = tmp_path / "custom_seed.db"
        monkeypatch.setenv("CHAESHIN_SEED_DB_PATH", str(custom))
        assert default_seed_db_path() == str(custom)

    def test_default_seed_db_path_expands_tilde_in_env(self, monkeypatch):
        # env 값에 ~ 가 들어있어도 literal "~" 디렉토리가 아니라 home 확장.
        monkeypatch.setenv("CHAESHIN_SEED_DB_PATH", "~/seed-tilde-test.db")
        out = default_seed_db_path()
        assert "~" not in out
        assert out.endswith("/seed-tilde-test.db")

    def test_default_seed_db_path_under_store_dir(self, monkeypatch, tmp_path: Path):
        monkeypatch.delenv("CHAESHIN_SEED_DB_PATH", raising=False)
        monkeypatch.setenv("CHAESHIN_STORE_DIR", str(tmp_path))
        assert default_seed_db_path() == str(tmp_path / "seed.db")

    def test_seed_store_round_trip(self, tmp_path: Path):
        path = tmp_path / "seed.db"
        store = open_seed_store(db_path=str(path))
        cid = store.retain(_case("rt"))

        store2 = open_seed_store(db_path=str(path))
        assert store2.get_case_by_id(cid) is not None
