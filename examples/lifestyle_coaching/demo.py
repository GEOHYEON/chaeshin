"""Lifestyle coaching demo — 만성피로 직장인 3개월 리셋 플랜.

scenario_ko.md 의 6개 시나리오(성공·연락두절·번아웃실패·cascade·재사용)를
코드로 재현한다. 의료 예시와 평행 구조이지만 도구·용어 전부 비의료.

실행:
    uv run python -m examples.lifestyle_coaching.demo
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
# 클라이언트 프로필 (가상)
# ─────────────────────────────────────────────────────────────────────────────

CLIENT_A = {
    "label": "박OO (34, 남)",
    "role": "스타트업 PM",
    "work_hours": "60-70h/week",
    "sleep_avg_h": 5.5,
    "exercise_last_6m": 0,
    "drink_per_week": 3.5,
    "prior_failures": ["헬스장 1주 후 이탈 × 2회"],
    "keywords": ["만성피로", "번아웃근접", "스타트업", "반복실패", "야근"],
}

CLIENT_B = {
    "label": "이OO (31, 여)",
    "role": "스타트업 마케터",
    "constraints": ["새벽 미팅 있음", "자차 없음", "반려견 산책 저녁 고정"],
    "keywords": ["만성피로", "야근", "번아웃근접", "반려견"],
}


# ─────────────────────────────────────────────────────────────────────────────
# 헬퍼 — 생활습관 케이스 1건을 pending으로
# ─────────────────────────────────────────────────────────────────────────────


def _case(
    request: str,
    *,
    layer: str,
    depth: int,
    nodes: list[GraphNode],
    edges: list[GraphEdge] | None = None,
    category: str = "lifestyle-coaching/reset",
    keywords: list[str] | None = None,
    parent_case_id: str = "",
    parent_node_id: str = "",
    deadline_weeks: int | None = None,
) -> Case:
    meta = CaseMetadata(
        source="lifestyle-coaching-demo",
        layer=layer,
        depth=depth,
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
        solution=Solution(tool_graph=ToolGraph(nodes=nodes, edges=edges or [])),
        outcome=Outcome(status="pending"),
        metadata=meta,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 트리 빌더
# ─────────────────────────────────────────────────────────────────────────────


def build_reset_tree(store: CaseStore, client: dict) -> dict[str, str]:
    """3개월 리셋 플랜 L4→L1 트리를 pending으로 저장."""
    ids: dict[str, str] = {}

    # ─── L4 root ──────────────────────────────────────────
    root = _case(
        request=f"3개월 생활 리셋 ({client['label']})",
        layer="L4",
        depth=3,
        nodes=[
            GraphNode(id="intake", tool="compose", note="현재 패턴 파악"),
            GraphNode(id="stratify", tool="compose", note="리스크·현실성"),
            GraphNode(id="plan", tool="compose", note="3개월 구조"),
            GraphNode(id="accountability", tool="compose", note="이탈 방지망"),
        ],
        edges=[
            GraphEdge(from_node="intake", to_node="stratify"),
            GraphEdge(from_node="stratify", to_node="plan"),
            GraphEdge(from_node="plan", to_node="accountability"),
        ],
        keywords=client["keywords"],
        deadline_weeks=12,
    )
    ids["L4"] = store.retain(root)

    # ─── L3 plan (4개 L2 자식) — 최소 부하 원칙 ─────────────
    plan = _case(
        request="3개월 구조 — 최소 부하로 시작",
        layer="L3",
        depth=2,
        nodes=[
            GraphNode(id="sleep", tool="compose", note="수면 앵커"),
            GraphNode(id="movement", tool="compose", note="매일 10분 움직임"),
            GraphNode(id="meal", tool="compose", note="식사 규칙 1개"),
            GraphNode(id="alcohol", tool="compose", note="주 1회 안 마시는 날"),
        ],
        edges=[
            GraphEdge(from_node="sleep", to_node="movement"),
            GraphEdge(from_node="movement", to_node="meal"),
            GraphEdge(from_node="meal", to_node="alcohol"),
        ],
        parent_case_id=ids["L4"],
        parent_node_id="plan",
        deadline_weeks=2,  # 2주 뒤 재조정 세션
    )
    ids["L3_plan"] = store.retain(plan)
    store.link_parent_child(ids["L4"], ids["L3_plan"], "plan")

    # ─── L2 수면 앵커 ─────────────────────────────────────
    sleep = _case(
        request="수면 앵커 — 카페인·술 차단 1시간 전",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(id="caf", tool="custom",
                      note="취침 1시간 전 카페인/술 차단 규칙"),
            GraphNode(id="nudge", tool="content_nudge",
                      params_hint={"topic": "수면위생 3분 영상"}),
        ],
        parent_case_id=ids["L3_plan"],
        parent_node_id="sleep",
    )
    ids["L2_sleep"] = store.retain(sleep)
    store.link_parent_child(ids["L3_plan"], ids["L2_sleep"], "sleep")

    # ─── L2 움직임 앵커 — 10분 (시나리오에서 고아화될 후보) ─
    movement = _case(
        request="움직임 앵커 — 매일 10분 홈운동",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(id="home10", tool="workout_propose",
                      params_hint={"minutes": 10, "equipment": "none"},
                      note="홈 10분 루틴"),
            GraphNode(id="lunchwalk", tool="walk_reminder",
                      params_hint={"time": "점심 직후"}),
        ],
        parent_case_id=ids["L3_plan"],
        parent_node_id="movement",
        # 고아화 → failure verdict 이후 유사 클라이언트 retrieve 시 warning으로 뜨도록 공통 키워드 부여
        keywords=["만성피로", "번아웃근접", "스타트업", "홈운동", "반복실패"],
    )
    ids["L2_movement"] = store.retain(movement)
    store.link_parent_child(ids["L3_plan"], ids["L2_movement"], "movement")

    # ─── L2 술 규칙 ──────────────────────────────────────
    alcohol = _case(
        request="주 1회 '안 마시는 날' — 화요일",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(id="rule", tool="custom",
                      note="매주 화요일 = 물의 날"),
        ],
        parent_case_id=ids["L3_plan"],
        parent_node_id="alcohol",
    )
    ids["L2_alcohol"] = store.retain(alcohol)
    store.link_parent_child(ids["L3_plan"], ids["L2_alcohol"], "alcohol")

    return ids


# ─────────────────────────────────────────────────────────────────────────────
# 시연
# ─────────────────────────────────────────────────────────────────────────────


def section(title: str):
    print("\n" + "═" * 68)
    print("  " + title)
    print("═" * 68)


def walk_tree(store: CaseStore, case_id: str, indent: int = 0):
    case = store.get_case_by_id(case_id)
    if not case:
        return
    pad = "  " * indent
    m = case.metadata
    deadline = m.deadline_at[:10] if m.deadline_at else "—"
    print(
        f"{pad}[{m.layer} d={m.depth}] {case.problem_features.request}"
    )
    print(
        f"{pad}  id={m.case_id[:8]} status={case.outcome.status}"
        f" deadline={deadline} kids={len(m.child_case_ids)}"
    )
    for cid in m.child_case_ids:
        walk_tree(store, cid, indent + 1)


def main():
    tmp = tempfile.TemporaryDirectory()
    db_path = Path(tmp.name) / "chaeshin-lifestyle.db"
    backend = SQLiteBackend(db_path)
    events = EventLog(backend, session_id="lifestyle-coaching-demo")
    store = CaseStore(backend=backend, auto_load=False)

    # ───────── T0 — 인테이크 ─────────
    section(f"T0 — 인테이크 ({CLIENT_A['label']})")
    print("코치: 과부하 플랜 2회 실패 이력. 번아웃 근접. 최소 부하로 시작하는 전략.\n")
    ids_a = build_reset_tree(store, CLIENT_A)
    events.record("decompose_context", {"client": CLIENT_A["label"]},
                  case_ids=[ids_a["L4"]])
    walk_tree(store, ids_a["L4"])

    # ───────── T+1주 — 피드백만 ─────────
    section("T+1주 — 첫 체크인 (verdict 보류, 피드백만 기록)")
    store.add_feedback(
        ids_a["L2_movement"],
        feedback="점심 걷기는 자연스러움, 10분 홈운동은 '저녁으로 미루다 까먹음' 패턴",
        feedback_type="modify",
    )
    events.record("feedback", {"pattern": "점심 걷기 > 홈운동"},
                  case_ids=[ids_a["L2_movement"]])
    mv = store.get_case_by_id(ids_a["L2_movement"])
    print(f"L2_movement feedback_count={mv.metadata.feedback_count}, "
          f"status={mv.outcome.status}  ← 1주차는 pending 유지")

    # ───────── T+2주 — Cascading revise ─────────
    section("T+2주 — 재조정 세션. L3 plan 그래프를 손본다 (cascade)")
    print("코치 진단: 홈운동 노드가 안 맞음. 걷기는 잘 붙었으니 그걸 앵커로 이식.")
    print("→ movement 노드 제거, walking_core + strength_snack 두 개로 쪼갬.\n")

    revised = store.revise_graph(
        ids_a["L3_plan"],
        nodes=[
            {"id": "sleep", "tool": "compose"},
            {"id": "walking_core", "tool": "compose",
             "note": "점심 걷기 유지 + 20분으로 연장"},
            {"id": "strength_snack", "tool": "compose",
             "note": "양치할 때 스쿼트 10회"},
            {"id": "meal", "tool": "compose"},
            {"id": "alcohol", "tool": "compose"},
        ],
        edges=[
            {"from": "sleep", "to": "walking_core"},
            {"from": "walking_core", "to": "strength_snack"},
            {"from": "strength_snack", "to": "meal"},
            {"from": "meal", "to": "alcohol"},
        ],
        cascade=True,
        reason="홈운동 안 붙음. 걷기를 앵커로 확장 + 의지 안 드는 스트렝스 스낵 추가.",
    )
    events.record(
        "revise",
        {
            "added": revised["added_nodes"],
            "removed": revised["removed_nodes"],
            "orphaned": revised["orphaned_children"],
        },
        case_ids=[ids_a["L3_plan"]] + revised["orphaned_children"],
    )
    print(f"added:    {revised['added_nodes']}")
    print(f"removed:  {revised['removed_nodes']}")
    print(f"retained: {revised['retained_nodes']}  ← sleep/meal/alcohol은 잘 되고 있어서 건드리지 않음")
    print(f"orphaned children: {[cid[:8] for cid in revised['orphaned_children']]}")

    if revised["orphaned_children"]:
        orphan = store.get_case_by_id(revised["orphaned_children"][0])
        print(f"\n고아 케이스 '{orphan.problem_features.request}':")
        print(f"  outcome.status: pending (되돌아감)")
        print(f"  feedback_log: {orphan.metadata.feedback_log[-1]}")

    # ───────── 고아 L2는 실패로 클로즈 (데이터 자산화) ─────────
    section("고아 L2 — failure로 명시 클로즈 (다음 유사 클라이언트의 warning이 된다)")
    store.set_verdict(
        revised["orphaned_children"][0],
        status="failure",
        note="번아웃 근접 클라이언트에게 10분 홈운동은 '저녁 미루기'로 이탈. "
             "대안: 걷기 연장 + 일상 삽입형 스트렝스.",
    )
    events.record("verdict", {"status": "failure"},
                  case_ids=[revised["orphaned_children"][0]])
    print(f"→ 이 L2는 앞으로 retrieve warnings에 노출됨.")

    # ───────── T+12주 — L4 success verdict ─────────
    section("T+12주 — 종료 세션: L4 성공 verdict")
    store.set_verdict(
        ids_a["L4"],
        status="success",
        note="수면 평균 1h↑, 에너지 3→4, 본인: '다음 단계 가보고 싶어요.' "
             "지속 가능 습관 3개 정착.",
    )
    events.record("verdict", {"status": "success"}, case_ids=[ids_a["L4"]])
    root = store.get_case_by_id(ids_a["L4"])
    print(f"L4 status: {root.outcome.status}")
    print(f"  verdict_note: {root.outcome.verdict_note}")

    # ───────── 6개월 후 유사 클라이언트 ─────────
    section(f"T+6개월 — 유사 클라이언트 ({CLIENT_B['label']}) 인입")
    print("같은 프로파일(스타트업·만성피로·번아웃근접)에 반려견 제약 추가.")
    print("→ retrieve로 박OO 트리 + 고아 L2 실패 기록까지 함께 받음.\n")

    probe = ProblemFeatures(
        request="30대 스타트업 만성피로 생활 리셋",
        category="lifestyle-coaching/reset",
        keywords=CLIENT_B["keywords"],
    )
    result = store.retrieve_with_warnings(probe, top_k=3, top_k_failures=3)
    events.record(
        "retrieve",
        {
            "query": probe.request,
            "n_successes": len(result["cases"]),
            "n_failures": len(result["warnings"]),
            "n_pending": len(result.get("pending", [])),
        },
        case_ids=[c.metadata.case_id for c, _ in result["cases"]],
    )

    print("successes (재사용 후보):")
    for c, s in result["cases"][:3]:
        print(f"  • [{c.metadata.layer}] sim={s:.3f} — {c.problem_features.request}")
    print("\nwarnings (피할 안티패턴):")
    for c, s in result["warnings"][:3]:
        print(f"  ⚠ [{c.metadata.layer}] sim={s:.3f} — {c.problem_features.request}")
        if c.outcome.verdict_note:
            print(f"    교훈: {c.outcome.verdict_note[:70]}...")
    print(f"\npending (미결 유사): {len(result.get('pending', []))}")

    # ───────── 클라이언트 B에 맞춘 diff ─────────
    section("클라이언트 B 맞춤화 — diff update")
    print("B의 특이사항: 저녁 반려견 산책 30분 고정. '점심 걷기'보다 이걸 앵커로.")
    ids_b = build_reset_tree(store, CLIENT_B)
    diff = store.update_case(
        ids_b["L2_movement"],
        patch={
            "problem_features": {
                "constraints": ["저녁 반려견 산책 30분 고정 — 이걸 앵커로"],
            },
        },
    )
    events.record("update", {"changed_fields": diff["changed_fields"]},
                  case_ids=[ids_b["L2_movement"]])
    print(f"변경된 필드: {diff['changed_fields']}")

    # ───────── 요약 ─────────
    section("저장소 상태 요약")
    total = len(store.cases)
    statuses: dict[str, int] = {}
    for c in store.cases:
        statuses[c.outcome.status] = statuses.get(c.outcome.status, 0) + 1
    print(f"total cases: {total}")
    print(f"status distribution: {statuses}")
    print(f"events recorded: {backend.event_count()}")
    print(
        "\n→ pending은 클라이언트 B의 12주 verdict까지 유지. 코치가 명시적으로 "
        "성공/실패 내리는 것이 원칙 — 자동 추론 없음."
    )

    tmp.cleanup()


if __name__ == "__main__":
    main()
