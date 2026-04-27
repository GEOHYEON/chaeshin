"""CLI seed subcommands smoke tests — list/export/import 라운드트립.

generate / promote 는 OPENAI_API_KEY 또는 main DB 와 얽혀있어 unit 으로 별도 검증.
여기선 seed_cmd 의 함수를 직접 호출 (subprocess 띄우지 않음).
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from chaeshin.case_store import CaseStore
from chaeshin.cli import seed_cmd
from chaeshin.schema import (
    Case,
    CaseMetadata,
    GraphNode,
    Outcome,
    ProblemFeatures,
    Solution,
    ToolGraph,
)
from chaeshin.seed import open_seed_store
from chaeshin.seed.promoter import PROMOTED_PREFIX
from chaeshin.storage.sqlite_backend import SQLiteBackend


def _case(request: str) -> Case:
    return Case(
        problem_features=ProblemFeatures(request=request, category="cli", keywords=[request]),
        solution=Solution(
            tool_graph=ToolGraph(nodes=[GraphNode(id="n1", tool="Bash", note=request)])
        ),
        outcome=Outcome(status="pending"),
        metadata=CaseMetadata(source="seed:cli"),
    )


class TestSeedExportImport:
    def test_round_trip(self, tmp_path: Path, capsys):
        seed_path = tmp_path / "seed.db"
        out_path = tmp_path / "dump.json"

        store = open_seed_store(db_path=str(seed_path))
        for r in ("a", "b", "c"):
            store.retain(_case(r))
        del store

        # export
        ns = argparse.Namespace(path=str(out_path), db=str(seed_path))
        rc = seed_cmd.cmd_export(ns)
        assert rc == 0
        assert out_path.exists()

        # 새 seed.db 에 import
        new_seed = tmp_path / "seed2.db"
        ns2 = argparse.Namespace(path=str(out_path), db=str(new_seed))
        rc = seed_cmd.cmd_import(ns2)
        assert rc == 0

        new_store = open_seed_store(db_path=str(new_seed))
        requests = sorted(c.problem_features.request for c in new_store.cases)
        assert requests == ["a", "b", "c"]


class TestSeedListFilter:
    def test_filter_by_topic(self, tmp_path: Path, capsys):
        seed_path = tmp_path / "seed.db"
        store = open_seed_store(db_path=str(seed_path))

        a = _case("alpha")
        a.metadata.source = "seed:topicA"
        b = _case("beta")
        b.metadata.source = "seed:topicB"
        store.retain(a)
        store.retain(b)
        del store

        ns = argparse.Namespace(topic="topicA", db=str(seed_path))
        seed_cmd.cmd_list(ns)
        out = capsys.readouterr().out
        # structlog 로그가 섞일 수 있으므로 마지막 JSON 객체 블록만 추출
        start = out.rfind("{\n  \"total\":")
        end = out.rfind("}")
        payload = json.loads(out[start : end + 1])
        requests = [c["request"] for c in payload["cases"]]
        assert "alpha" in requests
        assert "beta" not in requests


class TestSeedPromoteCli:
    def test_promote_via_cmd(self, tmp_path: Path, monkeypatch, capsys):
        seed_path = tmp_path / "seed.db"
        main_path = tmp_path / "chaeshin.db"

        # seed 에 두 건 retain
        store = open_seed_store(db_path=str(seed_path))
        c1 = _case("one")
        c2 = _case("two")
        store.retain(c1)
        store.retain(c2)
        del store

        # _open_main_store 가 main_path 를 보도록 store dir 환경 override
        monkeypatch.setenv("CHAESHIN_STORE_DIR", str(tmp_path))

        ns = argparse.Namespace(
            ids=c1.metadata.case_id,
            all=False,
            force=False,
            seed_db=str(seed_path),
        )
        rc = seed_cmd.cmd_promote(ns)
        assert rc == 0

        # main DB 가 생성되고 1건이 들어가 있어야 함
        main_store = CaseStore(backend=SQLiteBackend(str(main_path)), auto_load=True)
        assert len(main_store.cases) == 1
        assert main_store.cases[0].metadata.source.startswith(PROMOTED_PREFIX)
