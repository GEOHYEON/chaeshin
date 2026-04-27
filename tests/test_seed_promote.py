"""Promoter 테스트 — 새 case_id 발급, promoted_from 마커, idempotent."""

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
from chaeshin.seed import open_seed_store, promote_cases
from chaeshin.seed.promoter import PROMOTED_PREFIX
from chaeshin.storage.sqlite_backend import SQLiteBackend


def _seed_case(request: str, source: str = "seed:test") -> Case:
    return Case(
        problem_features=ProblemFeatures(request=request, category="t", keywords=[request]),
        solution=Solution(
            tool_graph=ToolGraph(nodes=[GraphNode(id="n1", tool="Bash", note=request)])
        ),
        outcome=Outcome(status="pending"),
        metadata=CaseMetadata(source=source),
    )


def _open_main(tmp_path: Path) -> CaseStore:
    return CaseStore(backend=SQLiteBackend(str(tmp_path / "main.db")), auto_load=True)


class TestPromote:
    def test_new_id_and_marker(self, tmp_path: Path):
        seed = open_seed_store(db_path=str(tmp_path / "seed.db"))
        main = _open_main(tmp_path)
        c = _seed_case("hello")
        seed.retain(c)

        results = promote_cases(seed, main, [c.metadata.case_id])
        assert len(results) == 1
        old, new = results[0]
        assert old == c.metadata.case_id
        assert new and new != old

        promoted = main.get_case_by_id(new)
        assert promoted is not None
        assert promoted.metadata.source == f"{PROMOTED_PREFIX}{old}"
        assert promoted.outcome.status == "pending"

    def test_idempotent_skip(self, tmp_path: Path):
        seed = open_seed_store(db_path=str(tmp_path / "seed.db"))
        main = _open_main(tmp_path)
        c = _seed_case("hello")
        seed.retain(c)

        promote_cases(seed, main, [c.metadata.case_id])
        before = len(main.cases)

        results = promote_cases(seed, main, [c.metadata.case_id])
        after = len(main.cases)

        assert after == before
        assert results[0][1] == ""  # skipped

    def test_force_creates_another_copy(self, tmp_path: Path):
        seed = open_seed_store(db_path=str(tmp_path / "seed.db"))
        main = _open_main(tmp_path)
        c = _seed_case("hello")
        seed.retain(c)

        promote_cases(seed, main, [c.metadata.case_id])
        assert len(main.cases) == 1

        promote_cases(seed, main, [c.metadata.case_id], force=True)
        # force 면 같은 마커가 있어도 한 번 더 복사
        assert len(main.cases) == 2

    def test_missing_seed_id(self, tmp_path: Path):
        seed = open_seed_store(db_path=str(tmp_path / "seed.db"))
        main = _open_main(tmp_path)

        results = promote_cases(seed, main, ["nonexistent-id"])
        assert results == [("nonexistent-id", "")]
        assert len(main.cases) == 0

    def test_main_persistence_across_reload(self, tmp_path: Path):
        seed = open_seed_store(db_path=str(tmp_path / "seed.db"))
        main = _open_main(tmp_path)
        c = _seed_case("persist")
        seed.retain(c)

        promote_cases(seed, main, [c.metadata.case_id])

        # 새 store 로 다시 열어도 main 에 있어야 함
        main2 = _open_main(tmp_path)
        assert len(main2.cases) == 1
        assert main2.cases[0].metadata.source.startswith(PROMOTED_PREFIX)


class TestPromoteTopology:
    """v2: 입력에 부모-자식이 같이 있으면 토폴로지 보존 + id 재매핑."""

    def test_parent_child_keeps_link_with_remapped_ids(self, tmp_path: Path):
        seed = open_seed_store(db_path=str(tmp_path / "seed.db"))
        main = _open_main(tmp_path)
        parent = _seed_case("p")
        child = _seed_case("c")
        seed.retain(parent)
        seed.retain(child)
        seed.link_parent_child(parent.metadata.case_id, child.metadata.case_id, "n1")

        # 자식을 먼저 입력해도 결과는 부모 먼저 promote.
        results = promote_cases(
            seed,
            main,
            [child.metadata.case_id, parent.metadata.case_id],
        )
        ordered_olds = [o for o, _ in results]
        assert ordered_olds == [parent.metadata.case_id, child.metadata.case_id]

        new_parent_id = results[0][1]
        new_child_id = results[1][1]
        assert new_parent_id and new_child_id
        assert new_parent_id != parent.metadata.case_id
        assert new_child_id != child.metadata.case_id

        new_parent = main.get_case_by_id(new_parent_id)
        new_child = main.get_case_by_id(new_child_id)
        assert new_child.metadata.parent_case_id == new_parent_id
        assert new_child.metadata.parent_node_id == "n1"
        assert new_child_id in new_parent.metadata.child_case_ids

    def test_orphan_child_promoted_alone_clears_parent_link(self, tmp_path: Path):
        seed = open_seed_store(db_path=str(tmp_path / "seed.db"))
        main = _open_main(tmp_path)
        parent = _seed_case("p2")
        child = _seed_case("c2")
        seed.retain(parent)
        seed.retain(child)
        seed.link_parent_child(parent.metadata.case_id, child.metadata.case_id, "n1")

        # 자식만 promote — 부모는 main 에 없으니 parent_case_id 끊는다.
        results = promote_cases(seed, main, [child.metadata.case_id])
        new_id = results[0][1]
        promoted = main.get_case_by_id(new_id)
        assert promoted.metadata.parent_case_id == ""
        assert promoted.metadata.parent_node_id == ""
