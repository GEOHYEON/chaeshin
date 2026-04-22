"""lifestyle_coaching + ReAct + Chaeshin — OpenAI 키만 있으면 바로 돌아간다.

코치 에이전트가 ReAct 루프로 만성피로 직장인의 3개월 리셋 플랜을 설계하고,
2주 뒤 재조정 시점에 들어온 클라이언트 피드백을 반영해 L3 플랜 그래프를 수정한다.
수정으로 연결이 끊기는 자식 케이스는 자동으로 pending 회귀(cascade).

실행:
    export OPENAI_API_KEY=sk-...
    uv run python -m examples.lifestyle_coaching.react_demo
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from chaeshin.agents.react_agent import ReActAgent, ToolSpec
from examples._react_common import (
    build_adapter,
    build_store,
    chaeshin_tools,
    print_store_summary,
)


# ─────────────────────────────────────────────────────────────────────
# 클라이언트 프로필 + 도메인 도구 (mock)
# ─────────────────────────────────────────────────────────────────────

CLIENT = {
    "id": "cl-001",
    "label": "박OO (34M)",
    "role": "스타트업 PM",
    "work_hours": "주 60-70시간",
    "sleep_avg_h": 5.5,
    "exercise_last_6m": 0,
    "drink_per_week": 3.5,
    "prior_failures": ["헬스장 등록 → 1주 후 이탈 × 2회"],
    "real_motivation": "돌 지난 아이. '아빠가 먼저 지쳐있는 게 싫어요.'",
}


def sleep_snapshot(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"duration_h": 5.5, "efficiency": 0.78, "bedtime": "02:30", "source": "수면 앱 2주치"}


def meal_snapshot(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"days": 3, "note": "사진만 수집, 평가 없음"}


def daily_energy_log(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"avg_energy": 2.3, "weekday_low": 2.0, "weekend_higher": True}


def habit_checkin(args: Dict[str, Any]) -> Dict[str, Any]:
    week = int(args.get("week", 1))
    if week == 1:
        return {
            "week": 1,
            "kept": ["점심 걷기 4일", "카페인 차단 주 4일"],
            "skipped": ["10분 홈운동 (3주 합쳐 2번만)"],
            "notes": "홈운동 저녁에 하려다 까먹음",
        }
    if week == 2:
        return {
            "week": 2,
            "kept": ["점심 걷기 주 5회", "카페인 차단 주 5일"],
            "skipped": ["홈운동 여전히 안 붙음"],
            "notes": "걷기는 자연스럽게 됨. 홈운동 자체가 안 맞는 듯.",
        }
    return {"week": week, "note": "가상 점검"}


def workout_propose(args: Dict[str, Any]) -> Dict[str, Any]:
    minutes = int(args.get("minutes", 10))
    return {"exercise": "전신 서킷 (플랭크-스쿼트-런지)", "minutes": minutes}


def meal_rule_propose(args: Dict[str, Any]) -> Dict[str, Any]:
    context = args.get("context", "아침 공복")
    return {"rule": "물 한 컵 + 바나나", "context": context}


def walk_reminder(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"scheduled_at": args.get("time", "12:30"), "notification_id": "nt-01"}


def content_nudge(args: Dict[str, Any]) -> Dict[str, Any]:
    topic = args.get("topic", "수면위생 3분 영상")
    return {"content_id": f"nudge-{topic}", "length_sec": 180}


def session_book(args: Dict[str, Any]) -> Dict[str, Any]:
    when = args.get("when", "2주 후")
    return {"session_id": f"sess-{when}", "when": when}


def domain_tools() -> Dict[str, ToolSpec]:
    return {
        "sleep_snapshot": ToolSpec(
            name="sleep_snapshot",
            description="수면 앱에서 지난밤 데이터 가져오기.",
            example_input='{"client_id": "cl-001"}',
            fn=sleep_snapshot,
        ),
        "meal_snapshot": ToolSpec(
            name="meal_snapshot",
            description="식사 사진 수집 (평가 안 함).",
            example_input='{"client_id": "cl-001"}',
            fn=meal_snapshot,
        ),
        "daily_energy_log": ToolSpec(
            name="daily_energy_log",
            description="하루 에너지 점수 로그.",
            example_input='{"client_id": "cl-001"}',
            fn=daily_energy_log,
        ),
        "habit_checkin": ToolSpec(
            name="habit_checkin",
            description="주간 점검. week=1 은 1주차, week=2 는 2주차.",
            example_input='{"client_id": "cl-001", "week": 2}',
            fn=habit_checkin,
        ),
        "workout_propose": ToolSpec(
            name="workout_propose",
            description="부담 적은 운동 하나 제안.",
            example_input='{"minutes": 10, "equipment": "none"}',
            fn=workout_propose,
        ),
        "meal_rule_propose": ToolSpec(
            name="meal_rule_propose",
            description="한 줄짜리 식사 규칙 제안.",
            example_input='{"context": "아침 공복"}',
            fn=meal_rule_propose,
        ),
        "walk_reminder": ToolSpec(
            name="walk_reminder",
            description="걷기 리마인더 등록.",
            example_input='{"time": "12:30"}',
            fn=walk_reminder,
        ),
        "content_nudge": ToolSpec(
            name="content_nudge",
            description="짧은 글·영상 추천.",
            example_input='{"topic": "수면위생 3분"}',
            fn=content_nudge,
        ),
        "session_book": ToolSpec(
            name="session_book",
            description="다음 코칭 세션 예약.",
            example_input='{"when": "2주 후"}',
            fn=session_book,
        ),
    }


SYSTEM_HINT = f"""당신은 비의료 생활습관 코치 에이전트입니다.

클라이언트 프로필:
{CLIENT}

[도메인 규칙]
- 최소 부하 원칙. 네 갈래(잠·운동·식사·술)마다 L1 딱 하나씩만 제안.
- 이 클라이언트는 과부하 플랜으로 두 번 실패한 이력이 있음. 헬스장 기반 플랜은 피할 것.

[2부로 나뉘는 흐름 — 반드시 끝까지 따라갈 것]

### 1부) T0 — 플랜 수립

반드시 **여러 번 chaeshin_retain** 을 호출해서 계층 트리를 만드세요 (한 번만 하면 안 됨):

1) sleep_snapshot / daily_energy_log 등으로 현재 패턴 파악.
2) chaeshin_retain #1 — **L4 루트**:
   - layer="L4", depth=3
   - graph.nodes = [intake, stratify, plan, accountability]
   - → L4_id 기억.
3) chaeshin_retain #2 — **L3 "3개월 플랜 구조"**:
   - layer="L3", depth=2, parent_case_id=L4_id, parent_node_id="plan"
   - graph.nodes = [sleep, movement, meal, alcohol]
   - → L3_plan_id 기억.
4) chaeshin_retain #3 — **L2 "몸 쓰기 — 매일 10분"**:
   - layer="L2", depth=1, parent_case_id=L3_plan_id, parent_node_id="movement"
   - graph.nodes = workout_propose 및 walk_reminder 호출 포함.
   - → L2_movement_id 기억. **(2부에서 고아가 될 대상)**
5) chaeshin_retain #4 — **L2 "잠 앵커"**:
   - layer="L2", depth=1, parent_case_id=L3_plan_id, parent_node_id="sleep"
   - graph.nodes = content_nudge 같은 노드.

### 2부) T+2주 — 재조정

6) habit_checkin(week=2) 호출. 결과에 "홈운동 안 붙음" 패턴이 있으면 →
7) chaeshin_revise — **L3 plan 그래프를** 새로 씀:
   - case_id = L3_plan_id
   - nodes = [sleep, walking_core, strength_snack, meal, alcohol]
     ("movement" 제거, "walking_core" + "strength_snack" 추가)
   - reason = 이유 설명
   - cascade=True
8) 응답의 `orphaned_children`에 L2_movement_id 가 나올 것. Final Answer에 이 사실을 보고하세요.

[그 외]
- 각 retain은 pending. 판정은 코치가 나중에 직접 내립니다. chaeshin_verdict는 **호출하지 마세요**.
- revise는 반드시 한 번 호출하세요 (2부가 이 데모의 핵심)."""


USER_REQUEST = (
    f"{CLIENT['label']}의 3개월 생활 리셋 플랜을 세워주세요. "
    f"T0에서 L4부터 주요 L1까지 저장하고, 그 다음 T+2주 시점의 주간 점검 결과를 habit_checkin(week=2)로 받아서 "
    f"필요하면 chaeshin_revise로 L3 '3개월 플랜 구조' 그래프를 수정해주세요. "
    f"수정으로 인해 연결이 끊기는 자식 케이스(orphaned_children)를 보고하고 마치세요."
)


async def main():
    adapter = build_adapter()
    store, events, tmp = build_store(session_id="lifestyle-react")

    tools = {**chaeshin_tools(store, events, category="lifestyle-coaching/reset", source="lifestyle-react"),
             **domain_tools()}

    agent = ReActAgent(
        adapter=adapter,
        tools=tools,
        system_hint=SYSTEM_HINT,
        max_steps=35,
    )
    try:
        await agent.run(USER_REQUEST)
        print_store_summary(store, events)
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
