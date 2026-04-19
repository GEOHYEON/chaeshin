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
            GraphNode(id="intake", tool="compose", note="현재 패턴 파악하기"),
            GraphNode(id="stratify", tool="compose", note="위험 신호 · 현실성 체크"),
            GraphNode(id="plan", tool="compose", note="3개월 플랜 구조"),
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
        request="3개월 플랜 구조 — 최소 부하로 시작",
        layer="L3",
        depth=2,
        nodes=[
            GraphNode(id="sleep", tool="compose", note="잠 — 자기 1시간 전 카페인/술 끊기"),
            GraphNode(id="movement", tool="compose", note="몸 쓰기 — 매일 10분"),
            GraphNode(id="meal", tool="compose", note="식사 규칙 하나만"),
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

    # ─── L2 잠 — 자기 1시간 전 카페인·술 끊기 ────────────
    sleep = _case(
        request="잠 — 자기 1시간 전 카페인·술 끊기",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(id="caf", tool="custom",
                      note="자기 1시간 전 카페인/술 금지 규칙"),
            GraphNode(id="nudge", tool="content_nudge",
                      params_hint={"topic": "수면위생 3분 영상"}),
        ],
        parent_case_id=ids["L3_plan"],
        parent_node_id="sleep",
    )
    ids["L2_sleep"] = store.retain(sleep)
    store.link_parent_child(ids["L3_plan"], ids["L2_sleep"], "sleep")

    # ─── L2 몸 쓰기 — 매일 10분 (이 케이스가 2주차에 연결이 끊기는 대상) ─
    movement = _case(
        request="몸 쓰기 — 매일 10분 홈운동",
        layer="L2",
        depth=1,
        nodes=[
            GraphNode(id="home10", tool="workout_propose",
                      params_hint={"minutes": 10, "equipment": "none"},
                      note="집에서 10분 루틴"),
            GraphNode(id="lunchwalk", tool="walk_reminder",
                      params_hint={"time": "점심 직후"}),
        ],
        parent_case_id=ids["L3_plan"],
        parent_node_id="movement",
        # 나중에 연결이 끊기고 failure로 닫히면, 비슷한 클라이언트 retrieve 때 경고로 뜨도록 키워드 명시
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

    # ───────── T0 — 첫 상담 ─────────
    section(f"T0 — 첫 상담 ({CLIENT_A['label']})")
    print("코치 판단: 과부하 플랜으로 두 번 실패한 이력. 번아웃 근접.")
    print("최소 부하로 시작해서 관성부터 만드는 전략.\n")
    ids_a = build_reset_tree(store, CLIENT_A)
    events.record("decompose_context", {"client": CLIENT_A["label"]},
                  case_ids=[ids_a["L4"]])
    walk_tree(store, ids_a["L4"])

    # ───────── T+1주 — 피드백만 ─────────
    section("T+1주 — 첫 주간 점검 (판정 보류, 피드백만 기록)")
    store.add_feedback(
        ids_a["L2_movement"],
        feedback="점심 걷기는 자연스럽게 됨. 10분 홈운동은 '저녁에 하려다 까먹음' 패턴",
        feedback_type="modify",
    )
    events.record("feedback", {"pattern": "점심 걷기는 붙음 / 홈운동은 미뤄짐"},
                  case_ids=[ids_a["L2_movement"]])
    mv = store.get_case_by_id(ids_a["L2_movement"])
    print(f"'몸 쓰기 — 매일 10분' 피드백 {mv.metadata.feedback_count}건 누적,")
    print(f"상태는 '{mv.outcome.status}' 그대로  ← 1주차에는 성공/실패 판정 안 내림")

    # ───────── T+2주 — 플랜 구조 바꾸기 ─────────
    section("T+2주 — 플랜 다시 짜는 세션. L3 플랜 그래프를 뜯어고친다")
    print("코치 진단: 홈운동이 안 붙음. 잘 되고 있는 걷기를 중심으로 옮기고,")
    print("근력은 양치 타이밍에 끼워넣는 걸로 바꾼다.")
    print("→ 'movement' 노드 빼고, 'walking_core' + 'strength_snack' 두 개로 쪼갬.\n")

    revised = store.revise_graph(
        ids_a["L3_plan"],
        nodes=[
            {"id": "sleep", "tool": "compose"},
            {"id": "walking_core", "tool": "compose",
             "note": "점심 걷기 유지 + 20분으로 늘리기"},
            {"id": "strength_snack", "tool": "compose",
             "note": "양치할 때 스쿼트 10번"},
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
        reason="홈운동이 안 붙음. 잘 되고 있는 걷기를 중심으로 옮기고 근력은 양치 타이밍에 끼워넣음",
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
    print(f"새로 생긴 자리:  {revised['added_nodes']}")
    print(f"없어진 자리:    {revised['removed_nodes']}")
    print(f"그대로 둔 자리: {revised['retained_nodes']}  ← 잘 되고 있는 건 건드리지 않음")
    print(f"연결이 끊긴 자식: {[cid[:8] for cid in revised['orphaned_children']]}")

    if revised["orphaned_children"]:
        orphan = store.get_case_by_id(revised["orphaned_children"][0])
        print(f"\n'{orphan.problem_features.request}' 케이스는 붙어있던 자리가 사라짐:")
        print(f"  상태: success/pending → pending으로 돌아감")
        print(f"  feedback_log: {orphan.metadata.feedback_log[-1]}")

    # ───────── 연결 끊긴 L2는 failure로 닫기 ─────────
    section("연결 끊긴 케이스를 failure로 닫기 (앞으로 비슷한 경우에 경고로 뜬다)")
    store.set_verdict(
        revised["orphaned_children"][0],
        status="failure",
        note="번아웃 근접 상태에서 10분 홈운동은 '저녁에 하려다 까먹음'으로 이탈. "
             "대안: 걷기를 늘리고 근력은 일상 틈새에 끼워넣기.",
    )
    events.record("verdict", {"status": "failure"},
                  case_ids=[revised["orphaned_children"][0]])
    print("→ 이제 이 케이스는 retrieve 결과에서 경고(warnings)로 뜬다.")

    # ───────── T+12주 — L4 success ─────────
    section("T+12주 — 마지막 세션: L4 전체 성공 판정")
    store.set_verdict(
        ids_a["L4"],
        status="success",
        note="잠 평균 1시간 늘어남. 에너지 3→4. 본인 말: '다음 단계 가보고 싶어요.' "
             "지속 가능한 습관 세 개 정착.",
    )
    events.record("verdict", {"status": "success"}, case_ids=[ids_a["L4"]])
    root = store.get_case_by_id(ids_a["L4"])
    print(f"L4 상태: {root.outcome.status}")
    print(f"  판정 메모: {root.outcome.verdict_note}")

    # ───────── 6개월 뒤 비슷한 클라이언트 ─────────
    section(f"T+6개월 뒤 — 비슷한 클라이언트 ({CLIENT_B['label']})가 옴")
    print("같은 프로필(스타트업 · 만성피로 · 번아웃 근접)에 반려견 제약이 추가됨.")
    print("→ retrieve로 박OO 트리 + 닫아뒀던 실패 기록까지 같이 뜬다.\n")

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

    print("성공 사례 (가져다 쓸 후보):")
    for c, s in result["cases"][:3]:
        print(f"  • [{c.metadata.layer}] 유사도={s:.3f} — {c.problem_features.request}")
    print("\n경고 (과거에 안 먹혔던 패턴):")
    for c, s in result["warnings"][:3]:
        print(f"  ⚠ [{c.metadata.layer}] 유사도={s:.3f} — {c.problem_features.request}")
        if c.outcome.verdict_note:
            print(f"    교훈: {c.outcome.verdict_note[:70]}...")
    print(f"\n아직 판정 안 난 비슷한 케이스: {len(result.get('pending', []))}건")

    # ───────── 클라이언트 B 맞춤 수정 ─────────
    section("클라이언트 B에 맞게 수정 — diff만 덮어쓰기")
    print("B의 제약: 저녁마다 반려견 산책 30분 고정. 점심 걷기 대신 이걸 중심으로.")
    ids_b = build_reset_tree(store, CLIENT_B)
    diff = store.update_case(
        ids_b["L2_movement"],
        patch={
            "problem_features": {
                "constraints": ["저녁마다 반려견 산책 30분 고정 — 이걸 중심으로"],
            },
        },
    )
    events.record("update", {"changed_fields": diff["changed_fields"]},
                  case_ids=[ids_b["L2_movement"]])
    print(f"바뀐 필드: {diff['changed_fields']}")

    # ───────── 요약 ─────────
    section("저장소 현황 요약")
    total = len(store.cases)
    statuses: dict[str, int] = {}
    for c in store.cases:
        statuses[c.outcome.status] = statuses.get(c.outcome.status, 0) + 1
    print(f"전체 케이스: {total}건")
    print(f"상태별: {statuses}")
    print(f"기록된 이벤트: {backend.event_count()}건")
    print(
        "\n→ 아직 pending인 것들은 클라이언트 B의 12주 판정 때까지 그대로 둔다."
        "\n   코치가 직접 성공/실패를 찍는 게 원칙 — 자동 판단은 하지 않는다."
    )

    tmp.cleanup()


if __name__ == "__main__":
    main()
