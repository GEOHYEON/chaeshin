"""CaseStore 테스트 — CBR 검색, 저장, 직렬화."""

import json
from chaeshin.schema import (
    Case,
    CaseMetadata,
    GraphNode,
    GraphEdge,
    Outcome,
    ProblemFeatures,
    Solution,
    ToolGraph,
)
from chaeshin.case_store import CaseStore


def _make_case(
    request: str, category: str, keywords: list,
    satisfaction: float = 0.9, success: bool = True, error_reason: str = "",
) -> Case:
    return Case(
        problem_features=ProblemFeatures(
            request=request,
            category=category,
            keywords=keywords,
        ),
        solution=Solution(
            tool_graph=ToolGraph(
                nodes=[GraphNode(id="n1", tool="test")],
                edges=[],
            ),
        ),
        outcome=Outcome(success=success, user_satisfaction=satisfaction, error_reason=error_reason),
        metadata=CaseMetadata(source="test"),
    )


class TestRetrieve:
    def test_retrieve_by_keywords(self):
        """키워드 기반 유사 케이스 검색."""
        store = CaseStore()
        store.retain(_make_case("김치찌개", "찌개류", ["김치", "찌개", "묵은지"]))
        store.retain(_make_case("된장찌개", "찌개류", ["된장", "찌개", "두부"]))
        store.retain(_make_case("양꼬치", "구이류", ["양고기", "꼬치"]))

        problem = ProblemFeatures(
            request="김치찌개 해줘",
            category="찌개류",
            keywords=["김치", "찌개"],
        )
        results = store.retrieve(problem, top_k=3)

        assert len(results) == 3
        # 김치찌개가 1순위여야 함
        assert results[0][0].problem_features.request == "김치찌개"
        # 된장찌개가 2순위 (같은 카테고리 + "찌개" 키워드 공유)
        assert results[1][0].problem_features.request == "된장찌개"

    def test_retrieve_uses_raw_user_input_without_keywords(self):
        """keywords가 비어 있어도 원문 자체로 검색한다."""
        store = CaseStore()
        store.retain(_make_case("CI 캐시 오류 수정", "devops", ["CI", "cache", "pnpm"]))
        store.retain(_make_case("저녁 한상 알레르기 식단", "가정식", ["저녁", "한상", "3인분", "알레르기"]))

        problem = ProblemFeatures(
            request="저녁 한상 차리기 3인분 알레르기 있음",
            category="",
            keywords=[],
        )
        results = store.retrieve(problem, top_k=2)

        assert results[0][0].problem_features.request == "저녁 한상 알레르기 식단"
        assert results[0][1] > results[1][1]

    def test_embedding_retrieve_uses_hybrid_lexical_signal(self):
        """임베딩 점수가 같아도 원문/키워드 신호로 재랭킹한다."""
        store = CaseStore(embed_fn=lambda text: [1.0, 0.0])
        store.retain(_make_case("CI 캐시 오류 수정", "devops", ["CI", "cache", "pnpm"]))
        store.retain(_make_case("저녁 한상 알레르기 식단", "가정식", ["저녁", "한상", "3인분", "알레르기"]))

        problem = ProblemFeatures(
            request="저녁 한상 차리기 3인분 알레르기 있음",
            category="",
            keywords=[],
        )
        results = store.retrieve(problem, top_k=2)

        assert results[0][0].problem_features.request == "저녁 한상 알레르기 식단"

    def test_retrieve_empty_store(self):
        """빈 저장소에서 검색."""
        store = CaseStore()
        problem = ProblemFeatures(request="test", category="test", keywords=[])
        results = store.retrieve(problem)

        assert len(results) == 0

    def test_retrieve_best(self):
        """최적 케이스 1개 반환."""
        store = CaseStore(similarity_threshold=0.3)
        store.retain(_make_case("김치찌개", "찌개류", ["김치", "찌개"]))

        problem = ProblemFeatures(
            request="김치찌개",
            category="찌개류",
            keywords=["김치", "찌개"],
        )
        best = store.retrieve_best(problem)

        assert best is not None
        assert best.problem_features.request == "김치찌개"

    def test_retrieve_best_below_threshold(self):
        """유사도가 임계값 미만이면 None."""
        store = CaseStore(similarity_threshold=0.99)
        store.retain(_make_case("양꼬치", "구이류", ["양고기"]))

        problem = ProblemFeatures(
            request="김치찌개",
            category="찌개류",
            keywords=["김치"],
        )
        best = store.retrieve_best(problem)

        assert best is None

    def test_retrieve_excludes_revision_snapshots(self):
        """과거 snapshot은 retrieve 후보에서 제외한다."""
        store = CaseStore()
        case = _make_case("배포 절차", "devops", ["deploy"])
        case_id = store.retain(case)

        store.revise_graph(
            case_id,
            nodes=[{"id": "n1", "tool": "Bash"}, {"id": "n2", "tool": "Bash"}],
            reason="add verify step",
        )
        store.revise_graph(
            case_id,
            nodes=[{"id": "n2", "tool": "Bash"}, {"id": "n3", "tool": "Bash"}],
            reason="replace build step",
        )

        problem = ProblemFeatures(request="배포 절차", category="devops", keywords=["deploy"])
        results = store.retrieve(problem, top_k=10)

        assert len(store.cases) == 3  # HEAD + snapshots 2개
        assert len(results) == 1
        assert results[0][0].metadata.case_id == case_id
        assert results[0][0].metadata.is_head is True


class TestRetain:
    def test_retain_new_case(self):
        """새 케이스 저장."""
        store = CaseStore()
        case = _make_case("테스트", "test", ["a"])
        case_id = store.retain(case)

        assert case_id is not None
        assert len(store.cases) == 1

    def test_retain_update_existing(self):
        """동일 case_id 업데이트."""
        store = CaseStore()
        case = _make_case("테스트", "test", ["a"])
        store.retain(case)

        case.outcome.user_satisfaction = 0.95
        store.retain(case)

        assert len(store.cases) == 1
        assert store.cases[0].outcome.user_satisfaction == 0.95

    def test_retain_if_successful(self):
        """성공 + 만족도 기준 충족 시에만 저장."""
        store = CaseStore()

        # 성공 + 높은 만족도 → 저장됨
        good = _make_case("좋은 케이스", "test", ["a"], satisfaction=0.9)
        assert store.retain_if_successful(good) is not None

        # 성공 + 낮은 만족도 → 저장 안됨
        bad = _make_case("나쁜 케이스", "test", ["b"], satisfaction=0.3)
        assert store.retain_if_successful(bad) is None

        assert len(store.cases) == 1

    def test_record_usage(self):
        """사용 기록 업데이트."""
        store = CaseStore()
        case = _make_case("테스트", "test", ["a"])
        store.retain(case)
        case_id = case.metadata.case_id

        store.record_usage(case_id, 0.8)
        store.record_usage(case_id, 1.0)

        assert store.cases[0].metadata.used_count == 2
        assert store.cases[0].metadata.avg_satisfaction == 0.9


class TestRevisionChain:
    def test_revise_creates_snapshot_chain(self):
        """revise는 덮어쓰지 않고 snapshot을 남기며 previous 체인을 잇는다."""
        store = CaseStore()
        case = _make_case("그래프 수정", "feature", ["graph"])
        case_id = store.retain(case)

        first = store.revise_graph(
            case_id,
            nodes=[
                {"id": "n1", "tool": "Read"},
                {"id": "n2", "tool": "Edit"},
            ],
            reason="first revision",
        )
        second = store.revise_graph(
            case_id,
            nodes=[
                {"id": "n2", "tool": "Edit"},
                {"id": "n3", "tool": "Bash"},
            ],
            reason="second revision",
        )

        assert first["revision_index"] == 1
        assert second["revision_index"] == 2
        assert first["snapshot_case_id"] != second["snapshot_case_id"]

        head = store.get_case_by_id(case_id)
        history = store.get_history(case_id)
        assert len(history) == 3
        assert [c.metadata.revision_index for c in history] == [2, 1, 0]
        assert history[0].metadata.case_id == case_id
        assert history[0].metadata.is_head is True
        assert history[1].metadata.is_head is False
        assert history[2].metadata.is_head is False
        assert head.metadata.previous_case_id == second["snapshot_case_id"]
        assert history[1].metadata.previous_case_id == first["snapshot_case_id"]

    def test_diff_versions_reports_node_changes(self):
        store = CaseStore()
        case = _make_case("diff", "feature", ["diff"])
        case_id = store.retain(case)
        store.revise_graph(
            case_id,
            nodes=[
                {"id": "n1", "tool": "test", "note": "changed"},
                {"id": "n2", "tool": "Bash"},
            ],
            edges=[{"from": "n1", "to": "n2"}],
            reason="diff target",
        )
        history = store.get_history(case_id)

        diff = store.diff_versions(history[-1].metadata.case_id, history[0].metadata.case_id)

        assert diff["nodes"]["added"] == ["n2"]
        assert diff["nodes"]["removed"] == []
        assert diff["nodes"]["changed"] == ["n1"]
        assert diff["edges"]["added"] == [
            {
                "from_node": "n1",
                "to_node": "n2",
                "condition": None,
                "action": None,
                "priority": 0,
                "note": "",
            }
        ]

    def test_revert_restores_old_graph_as_new_revision(self):
        store = CaseStore()
        case = _make_case("revert", "feature", ["revert"])
        case_id = store.retain(case)
        store.revise_graph(
            case_id,
            nodes=[{"id": "n1", "tool": "Read"}, {"id": "n2", "tool": "Edit"}],
            reason="rev1",
        )
        store.revise_graph(
            case_id,
            nodes=[{"id": "n3", "tool": "Bash"}],
            reason="rev2",
        )

        result = store.revert(case_id, to_index=0, reason="restore initial")
        head = store.get_case_by_id(case_id)
        history = store.get_history(case_id)

        assert result["revision_index"] == 3
        assert result["reverted_to_index"] == 0
        assert [n.id for n in head.solution.tool_graph.nodes] == ["n1"]
        assert head.solution.tool_graph.nodes[0].tool == "test"
        assert len(history) == 4
        assert history[1].metadata.revision_index == 2  # revert 직전 HEAD가 snapshot으로 보존됨

    def test_revise_preserves_child_parent_case_id(self):
        """HEAD case_id가 고정되므로 자식 재연결이 필요 없다."""
        store = CaseStore()
        parent = _make_case("parent", "workflow", ["p"])
        parent.solution.tool_graph.nodes = [
            GraphNode(id="keep", tool="plan"),
            GraphNode(id="drop", tool="plan"),
        ]
        child = _make_case("child", "atomic", ["c"])
        parent_id = store.retain(parent)
        child_id = store.retain(child)
        store.link_parent_child(parent_id, child_id, "keep")

        store.revise_graph(
            parent_id,
            nodes=[
                {"id": "keep", "tool": "plan"},
                {"id": "new", "tool": "plan"},
            ],
            reason="replace one node",
        )

        reloaded_child = store.get_case_by_id(child_id)
        assert reloaded_child.metadata.parent_case_id == parent_id
        assert reloaded_child.metadata.parent_node_id == "keep"


class TestSerialization:
    def test_json_roundtrip(self):
        """JSON 직렬화 ↔ 역직렬화."""
        store = CaseStore()
        store.retain(_make_case("김치찌개", "찌개류", ["김치", "찌개"]))
        store.retain(_make_case("된장찌개", "찌개류", ["된장", "찌개"]))

        json_str = store.to_json()

        store2 = CaseStore()
        store2.load_json(json_str)

        assert len(store2.cases) == 2
        assert store2.cases[0].problem_features.request == "김치찌개"
        assert store2.cases[1].problem_features.request == "된장찌개"

    def test_load_from_file(self, tmp_path):
        """파일에서 케이스 로드."""
        cases = [
            {
                "problem_features": {
                    "request": "테스트",
                    "category": "test",
                    "keywords": ["a"],
                    "constraints": [],
                    "context": {},
                },
                "solution": {
                    "tool_graph": {
                        "nodes": [{"id": "n1", "tool": "test", "params_hint": {}, "note": "", "input_schema": {}, "output_schema": {}}],
                        "edges": [],
                        "parallel_groups": [],
                        "entry_nodes": ["n1"],
                        "max_loops": 3,
                    },
                },
                "outcome": {
                    "success": True,
                    "result_summary": "",
                    "tools_executed": 1,
                    "loops_triggered": 0,
                    "total_time_ms": 100,
                    "user_satisfaction": 0.9,
                    "details": {},
                },
                "metadata": {
                    "case_id": "test-001",
                    "created_at": "2026-01-01T00:00:00",
                    "updated_at": "2026-01-01T00:00:00",
                    "used_count": 0,
                    "avg_satisfaction": 0.0,
                    "source": "test",
                    "version": 1,
                    "tags": [],
                },
            }
        ]

        file_path = tmp_path / "cases.json"
        file_path.write_text(json.dumps(cases, ensure_ascii=False))

        store = CaseStore()
        store.load_json(file_path.read_text())

        assert len(store.cases) == 1
        assert store.cases[0].metadata.case_id == "test-001"


class TestFailureCases:
    def test_retain_failure(self):
        """실패 케이스 저장."""
        store = CaseStore()
        case = _make_case("실패 작업", "test", ["a"], success=True)
        case_id = store.retain_failure(case, error_reason="API rate limit")

        assert case_id is not None
        assert len(store.cases) == 1
        assert store.cases[0].outcome.success is False
        assert store.cases[0].outcome.error_reason == "API rate limit"

    def test_retrieve_with_warnings(self):
        """성공 케이스 + 안티패턴 경고 반환."""
        store = CaseStore()

        # 성공 케이스
        store.retain(_make_case("김치찌개 만들기", "찌개류", ["김치", "찌개"]))

        # 실패 케이스
        store.retain_failure(
            _make_case("김치찌개 전자레인지", "찌개류", ["김치", "찌개"]),
            error_reason="전자레인지로는 찌개를 끓일 수 없음",
        )

        problem = ProblemFeatures(
            request="김치찌개",
            category="찌개류",
            keywords=["김치", "찌개"],
        )
        result = store.retrieve_with_warnings(problem)

        assert len(result["cases"]) == 1
        assert result["cases"][0][0].outcome.success is True

        assert len(result["warnings"]) == 1
        assert result["warnings"][0][0].outcome.success is False
        assert "전자레인지" in result["warnings"][0][0].outcome.error_reason

    def test_promote_failure(self):
        """실패 케이스를 성공 케이스로 교체."""
        store = CaseStore()

        # 실패 케이스 저장
        failure = _make_case("배포 작업", "devops", ["deploy"], success=False, error_reason="timeout")
        store.retain(failure)
        failure_id = failure.metadata.case_id

        assert len(store.cases) == 1
        assert store.cases[0].outcome.success is False

        # 성공 케이스로 교체
        success = _make_case("배포 작업", "devops", ["deploy"], success=True)
        new_id = store.promote_failure(failure_id, success)

        assert new_id is not None
        assert len(store.cases) == 1
        assert store.cases[0].outcome.success is True
        assert store.cases[0].metadata.case_id != failure_id

    def test_promote_failure_not_found(self):
        """존재하지 않는 실패 케이스 교체 시도."""
        store = CaseStore()
        success = _make_case("테스트", "test", ["a"])
        assert store.promote_failure("nonexistent-id", success) is None

    def test_failure_case_json_roundtrip(self):
        """실패 케이스 JSON 직렬화/역직렬화."""
        store = CaseStore()
        store.retain_failure(
            _make_case("실패", "test", ["a"]),
            error_reason="테스트 실패 사유",
        )

        json_str = store.to_json()
        store2 = CaseStore()
        store2.load_json(json_str)

        assert len(store2.cases) == 1
        assert store2.cases[0].outcome.success is False
        assert store2.cases[0].outcome.error_reason == "테스트 실패 사유"
