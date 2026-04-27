"""agents/orchestrator + reflection 정합성 스모크 테스트.

오래된 success=True 하드코딩을 제거한 뒤로 이 두 에이전트가 retain할 때
outcome.status가 항상 'pending' 으로 들어가야 한다 (사용자 verdict 권한 보호).

또 reflection.escalate가 고정 L1/L2/L3 가정 없이 임의 깊이에서 동작해야 한다.
"""

from __future__ import annotations

from chaeshin.agents.reflection import _bump_layer
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


class TestLayerBump:
    def test_l1_up(self):
        assert _bump_layer("L1", +1) == "L2"

    def test_l5_down(self):
        # 깊이 무제한 — L4/L5도 자연스럽게 이동
        assert _bump_layer("L5", -1) == "L4"

    def test_l1_down_clamps_to_l1(self):
        # 0 이하로 못 내려감
        assert _bump_layer("L1", -1) == "L1"

    def test_malformed_falls_back(self):
        assert _bump_layer("nonsense", +1) == "L1"
        assert _bump_layer("Lfoo", +1) == "L1"


class TestOrchestratorRetainStaysPending:
    """orchestrator의 _retain_tree 패턴 — Outcome.status='pending'으로 저장돼야 함.

    실제 OrchestratorAgent를 돌리려면 LLM이 필요하므로, 여기서는 같은 패턴이
    case_store + Outcome 모델 위에서 정상 작동하는지만 검증한다.
    """

    def _store(self, tmp_path):
        backend = SQLiteBackend(tmp_path / "ag.db")
        return CaseStore(backend=backend, auto_load=False)

    def test_retain_uses_pending_status(self, tmp_path):
        store = self._store(tmp_path)
        case = Case(
            problem_features=ProblemFeatures(request="x", category="t", keywords=[]),
            solution=Solution(
                tool_graph=ToolGraph(nodes=[GraphNode(id="n1", tool="echo")])
            ),
            outcome=Outcome(status="pending"),  # ← 새 정합화: 'pending'
            metadata=CaseMetadata(source="orchestrator"),  # layer/depth 는 derived
        )
        cid = store.retain(case)
        loaded = store.get_case_by_id(cid)
        assert loaded.outcome.status == "pending"
        assert loaded.outcome.success is False  # status에서 자동 동기화
        assert store.derive_layer(cid) == "L1"  # 자식 없음 → leaf


class TestReflectionEscalateDepthAware:
    """reflection.escalate는 depth 기반 일반화여야 한다 (L4/L5도 정상).

    실제 ReflectionAgent를 돌리려면 LLM이 필요하므로 _bump_layer 동작만 검증.
    """

    def test_l3_escalates_to_l4(self):
        # 새 상위가 L4가 되어야 함 (L3는 L2로 강등 — depth-1)
        assert _bump_layer("L3", +1) == "L4"
        assert _bump_layer("L3", -1) == "L2"

    def test_l4_escalates_to_l5(self):
        # 고정 3단계 가정 깨도 동작
        assert _bump_layer("L4", +1) == "L5"
