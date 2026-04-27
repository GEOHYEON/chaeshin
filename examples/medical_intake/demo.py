"""Medical intake demo — 신규 T2DM 환자 초진 시나리오.

Chaeshin의 세 가지 핵심 동작을 의료 맥락에서 보여준다:
  1. 계속 쪼개기 — L4부터 L1까지 tool 단일 호출 수준까지 내려간다
  2. 세 가지 상태 — retain은 pending으로 저장, 의료진의 verdict만 success/failure로 전환
  3. 비슷한 환자가 왔을 때 retrieve로 참고 트리 가져오고 diff만 덮어쓰기

실행:
    uv run python -m examples.medical_intake.demo

실행 결과: 콘솔에 각 단계가 순서대로 출력되며, 임시 tmp_path DB에 케이스가
저장됐다가 시나리오 끝에 삭제된다. 환자 정보는 모두 가상이다.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

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


# ─────────────────────────────────────────────────────────────────────────────
# 환자 프로필 (가상)
# ─────────────────────────────────────────────────────────────────────────────

PATIENT_A = {
    "label": "김OO (45M)",
    "hba1c": 7.2,
    "bmi": 28.4,
    "shift": "night-rotation",
    "barriers": ["economic", "shift-work", "limited-cooking-access"],
    "keywords": ["T2DM", "신환", "야간근무", "3교대", "경제적제약"],
}

PATIENT_B = {
    "label": "이OO (42F)",
    "hba1c": 7.0,
    "bmi": 26.1,
    "shift": "night-taxi",
    "barriers": ["shift-work", "no-smartphone"],
    "keywords": ["T2DM", "신환", "야간근무", "택시기사"],
}


# ─────────────────────────────────────────────────────────────────────────────
# 트리 빌더 — 환자 A의 L4부터 L1까지 한 번에 쌓기
# ─────────────────────────────────────────────────────────────────────────────


def _case(
    request: str,
    *,
    layer: str = "",  # 표시용/호출 호환만 — 저장 안 함, derived
    depth: int = 0,   # 표시용/호출 호환만 — 저장 안 함, derived
    nodes: list[GraphNode],
    edges: list[GraphEdge] | None = None,
    category: str = "primary-care/T2DM",
    keywords: list[str] | None = None,
    parent_case_id: str = "",
    parent_node_id: str = "",
    deadline_weeks: int | None = None,
) -> Case:
    """의료 케이스 한 건을 pending 상태로 만든다.

    ``layer``/``depth`` 는 더 이상 저장되지 않는다 (트리에서 derived). 인자는 데모
    호출부 호환을 위해 받지만 무시.
    """
    meta = CaseMetadata(
        source="medical-intake-demo",
        parent_case_id=parent_case_id,
        parent_node_id=parent_node_id,
        wait_mode="deadline",
    )
    if deadline_weeks:
        meta.deadline_at = (
            datetime.now() + timedelta(weeks=deadline_weeks)
        ).isoformat()
    return Case(
        problem_features=ProblemFeatures(
            request=request,
            category=category,
            keywords=keywords or [],
        ),
        solution=Solution(
            tool_graph=ToolGraph(nodes=nodes, edges=edges or [])
        ),
        outcome=Outcome(status="pending"),  # 의료 — 결과 확인 전까진 성공도 실패도 아님
        metadata=meta,
    )


def build_t2dm_tree(store: CaseStore, patient: dict) -> dict[str, str]:
    """환자 A의 L4부터 L1까지 트리 전체를 pending으로 저장. 반환값은 레이어별 case_id."""
    ids: dict[str, str] = {}

    # ─── L4 root ──────────────────────────────────────────
    root = _case(
        request=f"신환 T2DM 초진 — 개별 맞춤 관리 계획 ({patient['label']})",
        layer="L4",
        depth=3,
        nodes=[
            GraphNode(id="intake", tool="compose", note="생활습관 문진 묶음"),
            GraphNode(id="stratify", tool="compose", note="risk stratification"),
            GraphNode(id="plan", tool="compose", note="individualized plan"),
            GraphNode(id="followup", tool="compose", note="follow-up schedule"),
        ],
        edges=[
            GraphEdge(from_node="intake", to_node="stratify"),
            GraphEdge(from_node="stratify", to_node="plan"),
            GraphEdge(from_node="plan", to_node="followup"),
        ],
        keywords=patient["keywords"],
        deadline_weeks=12,
    )
    ids["L4"] = store.retain(root)

    # ─── L3 intake ────────────────────────────────────────
    intake = _case(
        request="생활습관 문진",
        layer="L3",
        depth=2,
        nodes=[
            GraphNode(id="diet", tool="compose"),
            GraphNode(id="activity", tool="compose"),
            GraphNode(id="sleep", tool="compose"),
            GraphNode(id="substance", tool="compose"),
            GraphNode(id="motivation", tool="compose"),
        ],
        parent_case_id=ids["L4"],
        parent_node_id="intake",
    )
    ids["L3_intake"] = store.retain(intake)
    store.link_parent_child(ids["L4"], ids["L3_intake"], "intake")

    # ─── L2 diet 평가 ─────────────────────────────────────
    diet_eval = _case(
        request="식이 평가",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(id="recall", tool="dietary_recall_24h",
                      note="FHIR Observation LOINC 9271-8"),
            GraphNode(id="fs", tool="food_security_screen",
                      note="HFSSM 2문항 / LOINC 88121-9"),
            GraphNode(id="korean", tool="custom",
                      note="김치 나트륨 + 탄수 비중 체크"),
        ],
        parent_case_id=ids["L3_intake"],
        parent_node_id="diet",
    )
    ids["L2_diet"] = store.retain(diet_eval)
    store.link_parent_child(ids["L3_intake"], ids["L2_diet"], "diet")

    # ─── L2 활동 평가 ─────────────────────────────────────
    activity_eval = _case(
        request="신체활동 평가",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(id="gpaq", tool="gpaq_activity",
                      note="FHIR Observation LOINC 82580-1"),
            GraphNode(id="commute", tool="custom", note="통근·직업 활동량"),
        ],
        parent_case_id=ids["L3_intake"],
        parent_node_id="activity",
    )
    ids["L2_activity"] = store.retain(activity_eval)
    store.link_parent_child(ids["L3_intake"], ids["L2_activity"], "activity")

    # ─── L3 plan (개별 맞춤) — intake 결과 기반으로 인스턴스화 ──
    plan = _case(
        request="개별 맞춤 관리 계획",
        layer="L3",
        depth=2,
        nodes=[
            GraphNode(id="meal", tool="compose", note="저예산 교대근무 식단"),
            GraphNode(id="activity", tool="compose", note="야간근무 운동 루틴"),
            GraphNode(id="med", tool="compose", note="약물 치료 시작"),
            GraphNode(id="goals", tool="compose", note="SMART 목표 설정"),
        ],
        edges=[
            GraphEdge(from_node="meal", to_node="activity"),
            GraphEdge(from_node="activity", to_node="med"),
            GraphEdge(from_node="med", to_node="goals"),
        ],
        parent_case_id=ids["L4"],
        parent_node_id="plan",
        deadline_weeks=12,
    )
    ids["L3_plan"] = store.retain(plan)
    store.link_parent_child(ids["L4"], ids["L3_plan"], "plan")

    # ─── L2 저예산 교대근무 식단 ─────────────────────
    meal_plan = _case(
        request="저예산 교대근무 식단",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(
                id="tailor",
                tool="meal_plan_tailored",
                params_hint={"budget": "low", "shift": "night-rotation"},
                note="CarePlan.activity — 주간 식단",
            ),
            GraphNode(id="conv_rules", tool="custom", note="편의점 조합 규칙"),
        ],
        parent_case_id=ids["L3_plan"],
        parent_node_id="meal",
        keywords=["편의점", "야간근무", "저예산"],
    )
    ids["L2_meal"] = store.retain(meal_plan)
    store.link_parent_child(ids["L3_plan"], ids["L2_meal"], "meal")

    # ─── L2 약물 치료 시작 (metformin 1차) ──────────────
    med = _case(
        request="메트포르민 1차 시작",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(
                id="propose",
                tool="medication_propose",
                params_hint={"first_line": "metformin", "dose": "500mg bid"},
                note="FHIR MedicationRequest",
            ),
            GraphNode(id="coach", tool="custom",
                      note="야간근무 복약 타이밍 코칭"),
        ],
        parent_case_id=ids["L3_plan"],
        parent_node_id="med",
    )
    ids["L2_med"] = store.retain(med)
    store.link_parent_child(ids["L3_plan"], ids["L2_med"], "med")

    return ids


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 시연
# ─────────────────────────────────────────────────────────────────────────────


def section(title: str):
    print("\n" + "═" * 68)
    print("  " + title)
    print("═" * 68)


def describe_case(store: CaseStore, case: Case, indent: int = 0):
    pad = "  " * indent
    meta = case.metadata
    status = case.outcome.status
    deadline = meta.deadline_at[:10] if meta.deadline_at else "—"
    layer = store.derive_layer(meta.case_id)
    depth = store.derive_depth(meta.case_id)
    print(
        f"{pad}[{layer} depth={depth}] {case.problem_features.request}"
    )
    print(
        f"{pad}  id={meta.case_id[:8]} status={status}"
        f" deadline={deadline} children={len(meta.child_case_ids)}"
    )


def walk_tree(store: CaseStore, case_id: str, indent: int = 0):
    case = store.get_case_by_id(case_id)
    if not case:
        return
    describe_case(store, case, indent)
    for child_id in case.metadata.child_case_ids:
        walk_tree(store, child_id, indent + 1)


def main():
    tmp = tempfile.TemporaryDirectory()
    db_path = Path(tmp.name) / "chaeshin-demo.db"
    backend = SQLiteBackend(db_path)
    events = EventLog(backend, session_id="medical-intake-demo")
    store = CaseStore(backend=backend, auto_load=False)

    # ───────────────── T0 — 환자 A 초진 ─────────────────
    section(f"T0 — 환자 A 초진 ({PATIENT_A['label']})")
    print("의료진 판단: 신규 T2DM · 야간 3교대 · 경제적 제약.")
    print("→ L4부터 L1까지 트리 전체를 '아직 판단 안 함(pending)' 상태로 저장.\n")

    ids_a = build_t2dm_tree(store, PATIENT_A)
    events.record("decompose_context", {"patient": PATIENT_A["label"]},
                  case_ids=[ids_a["L4"]])

    print("만들어진 트리:")
    walk_tree(store, ids_a["L4"])

    # ───────────────── T+4주 피드백만 ─────────────────
    section("T+4주 — 중간 외래 (판정 보류, 피드백만 기록)")
    store.add_feedback(
        ids_a["L2_meal"],
        feedback="편의점 조합 규칙이 잘 맞는다고 함 (김밥+두유+삶은달걀)",
        feedback_type="correct",
    )
    events.record("feedback", {"note": "편의점 조합 호응"},
                  case_ids=[ids_a["L2_meal"]])
    meal = store.get_case_by_id(ids_a["L2_meal"])
    print(f"L2_meal 피드백 {meal.metadata.feedback_count}건 누적, "
          f"상태는 '{meal.outcome.status}' 그대로")
    print("→ HbA1c 재측정 전이라 아직 성공/실패 판정 안 내림.")

    # ───────────────── T+12주 verdict=success ─────────────────
    section("T+12주 — HbA1c 7.2 → 6.5, 체중 -3.2kg. 의료진이 '성공' 판정")
    for key in ("L4", "L3_plan", "L2_meal", "L2_med"):
        store.set_verdict(
            ids_a[key],
            status="success",
            note="HbA1c 7.2→6.5, 편의점 조합 + 야간근무 운동 루틴 12주 유지",
        )
        events.record("verdict", {"status": "success"}, case_ids=[ids_a[key]])

    root = store.get_case_by_id(ids_a["L4"])
    print(f"L4 루트 상태: {root.outcome.status}, "
          f"판정 시각: {root.outcome.verdict_at[:19]}")
    print(f"  판정 메모: {root.outcome.verdict_note}")

    # ───────────────── T+8주 상황 재현 — L3 그래프 뜯어고치기 ─────
    section("상위 플랜 뜯어고치기 — L3 '개별 맞춤 관리 계획' 그래프를 손본다")
    print("가정: 8주차에 환자가 '야간 근무 때 약을 자주 놓친다'고 호소해서")
    print("의료진이 플랜 자체를 손봤다. 'med' 노드를 단일정 복약과 자가 모니터링")
    print("두 개로 쪼갠다. 기존 L2 '메트포르민 1차 시작'은 붙어있던 자리가 사라진다.\n")

    revise_result = store.revise_graph(
        ids_a["L3_plan"],
        nodes=[
            {"id": "meal", "tool": "compose"},
            {"id": "activity", "tool": "compose"},
            {"id": "med_simplified", "tool": "compose",
             "note": "1T metformin + 리마인더"},
            {"id": "self_monitor", "tool": "compose",
             "note": "주간 체중/FBS 자가 측정"},
            {"id": "goals", "tool": "compose"},
        ],
        edges=[
            {"from": "meal", "to": "activity"},
            {"from": "activity", "to": "med_simplified"},
            {"from": "med_simplified", "to": "self_monitor"},
            {"from": "self_monitor", "to": "goals"},
        ],
        cascade=True,
        reason="야간 근무 중 약 놓침 — 약물 노드를 단일정 복약 + 자가 모니터링으로 쪼갬",
    )
    events.record(
        "revise",
        {
            "added": revise_result["added_nodes"],
            "removed": revise_result["removed_nodes"],
            "orphaned": revise_result["orphaned_children"],
        },
        case_ids=[ids_a["L3_plan"]] + revise_result["orphaned_children"],
    )

    print(f"새로 생긴 자리:   {revise_result['added_nodes']}")
    print(f"없어진 자리:      {revise_result['removed_nodes']}")
    print(f"그대로 둔 자리:   {revise_result['retained_nodes']}")
    print(f"연결이 끊긴 자식: "
          f"{[cid[:8] for cid in revise_result['orphaned_children']]}")

    if revise_result["orphaned_children"]:
        orphan = store.get_case_by_id(revise_result["orphaned_children"][0])
        print(f"\n'{orphan.problem_features.request}' 케이스는 붙어있던 자리가 사라짐:")
        print(f"  상태: success → {orphan.outcome.status}")
        print(f"  feedback_log: {orphan.metadata.feedback_log[-1]}")
    print("\n→ 의료진의 다음 결정:")
    print("  · 새로 생긴 자리 아래에 새 L2 케이스를 만들어 붙이기")
    print("  · 연결 끊긴 케이스는 내용을 수정해서 재연결 / failure로 닫기 / 지우기 중 선택")

    # ───────────────── 6개월 뒤 비슷한 환자 ─────────────────
    section(f"T+6개월 뒤 — 비슷한 환자 {PATIENT_B['label']}가 옴")
    print("다른 의료진이 비슷한 프로필의 신환을 본다.")
    print("→ retrieve로 A의 성공 트리를 후보로 가져온다.\n")

    probe = ProblemFeatures(
        request="야간 근무 T2DM 신환 초진 개별 맞춤 관리 계획",
        category="primary-care/T2DM",
        keywords=PATIENT_B["keywords"],
    )
    result = store.retrieve_with_warnings(probe, top_k=3, top_k_failures=3)
    events.record(
        "retrieve",
        {
            "query": probe.request,
            "n_successes": len(result["cases"]),
            "n_pending": len(result.get("pending", [])),
            "n_failures": len(result["warnings"]),
        },
        case_ids=[c.metadata.case_id for c, _ in result["cases"]],
    )
    print("성공 사례 (가져다 쓸 후보):")
    for c, s in result["cases"][:3]:
        print(
            f"  • [{store.derive_layer(c.metadata.case_id)}] 유사도={s:.3f} "
            f"— {c.problem_features.request}"
        )
    print(f"경고 (과거에 안 먹혔던 패턴): {len(result['warnings'])}건")
    print(f"아직 판정 안 난 비슷한 케이스: {len(result.get('pending', []))}건")

    # ───────────────── 환자 B에 맞춘 diff 덮어쓰기 ─────────────────
    section("환자 B에 맞게 수정 — diff만 덮어쓰기")
    print("다른 점: 피처폰 사용 → patient_message_send 채널을 SMS로 바꾼다.")

    # 환자 A의 L2_meal을 바탕으로 B 전용 트리를 만들고 SMS 제약만 덮어쓰기
    ids_b = build_t2dm_tree(store, PATIENT_B)

    diff = store.update_case(
        ids_b["L2_meal"],
        patch={
            "problem_features": {
                "constraints": ["SMS로만 연락 가능", "편의점 접근 양호"],
            },
        },
    )
    events.record("update", {"changed_fields": diff["changed_fields"]},
                  case_ids=[ids_b["L2_meal"]])
    print(f"바뀐 필드: {diff['changed_fields']}")

    # ───────────────── 저장소 요약 ─────────────────
    section("저장소 현황 요약")
    total = len(store.cases)
    status_counts: dict[str, int] = {}
    for c in store.cases:
        status_counts[c.outcome.status] = status_counts.get(c.outcome.status, 0) + 1
    print(f"전체 케이스: {total}건")
    print(f"상태별: {status_counts}")
    print(f"기록된 이벤트: {backend.event_count()}건")
    print(
        "\n→ 아직 pending인 케이스들은 환자 B의 12주 추적이 끝날 때까지 그대로 둔다."
        "\n   의료진이 HbA1c 재검 결과를 보고 그때 직접 판정을 내린다."
    )

    tmp.cleanup()


if __name__ == "__main__":
    main()
