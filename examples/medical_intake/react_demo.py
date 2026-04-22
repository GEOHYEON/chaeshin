"""medical_intake + ReAct + Chaeshin — OpenAI 키만 있으면 바로 돌아간다.

초진 에이전트가 ReAct 루프로 신규 T2DM 환자의 개별 맞춤 관리 계획을 세운다.
과거 비슷한 케이스가 있으면 재사용하고, 없으면 재귀 분해로 L4→L1 트리를 만든다.
모든 retain은 pending으로 들어가고, 12주 후 실제 지표를 본 의료진이 판정한다.

실행:
    export OPENAI_API_KEY=sk-...
    uv run python -m examples.medical_intake.react_demo
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
# 가상 환자 프로필 + 도구
# ─────────────────────────────────────────────────────────────────────

PATIENT = {
    "id": "pt-001",
    "label": "김OO (45M)",
    "hba1c": 7.2,
    "fbs": 142,
    "bmi": 28.4,
    "bp": "134/86",
    "shift": "night-rotation-3shift",
    "job": "물류센터",
    "smoking": "ex-smoker (금연 5년)",
    "drink": "주 2회 소주 1병",
    "family_hx": "모 T2DM · 부 AMI 58세",
    "economic": "외벌이, 주 70시간 근무, 편의점·야식 위주",
}


def dietary_recall_24h(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "patient_id": args.get("patient_id", PATIENT["id"]),
        "kcal_est": 2800,
        "carb_ratio": 0.62,
        "meals": [
            {"type": "편의점 삼각김밥+컵라면", "time": "23:00"},
            {"type": "야식 치킨 반 마리", "time": "03:00"},
            {"type": "아침 거름", "time": "08:00"},
        ],
        "note": "야간 근무 특성상 1일 3끼 패턴 아님",
    }


def food_security_screen(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"score": 1, "insecure": True, "barriers": ["시간 제약", "저예산"]}


def gpaq_activity(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"met_minutes_week": 240, "sedentary_hours": 12, "note": "직업상 경도 활동만"}


def sleep_chronotype(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"avg_sleep_h": 5.5, "shift_pattern": "3교대", "quality": "poor"}


def motivation_readiness(args: Dict[str, Any]) -> Dict[str, Any]:
    domain = args.get("domain", "diet")
    return {"domain": domain, "stage": "preparation"}


def cvd_risk_calc(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"risk_10yr_pct": 9.4, "category": "intermediate", "note": "부 AMI 가족력 반영"}


def medication_propose(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "drug": "metformin",
        "dose": "500mg bid → 1000mg bid 2주 후",
        "contraindications": None,
        "rationale": "HbA1c 7.2, eGFR 정상. 1차 표준 치료.",
    }


def meal_plan_tailored(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "plan": "편의점 조합 규칙 + 야근 전후 식사 순서 조정",
        "examples": ["샐러드+삶은달걀+두유", "김밥+계란+바나나"],
        "weekly_cost_krw": 55000,
    }


def followup_schedule(args: Dict[str, Any]) -> Dict[str, Any]:
    weeks = int(args.get("interval_weeks", 4))
    tests = args.get("tests", ["FBS"])
    return {"interval_weeks": weeks, "tests": tests, "appointment_id": f"appt-{weeks}w"}


def goal_set(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"goal_id": "goal-001", "target": args.get("target", "HbA1c<6.8"), "horizon": args.get("horizon", "12w")}


def domain_tools() -> Dict[str, ToolSpec]:
    return {
        "dietary_recall_24h": ToolSpec(
            name="dietary_recall_24h",
            description="24시간 식이 회상. FHIR Observation LOINC 9271-8.",
            example_input='{"patient_id": "pt-001"}',
            fn=dietary_recall_24h,
        ),
        "food_security_screen": ToolSpec(
            name="food_security_screen",
            description="식품 불안정성 스크리닝 (HFSSM).",
            example_input='{"patient_id": "pt-001"}',
            fn=food_security_screen,
        ),
        "gpaq_activity": ToolSpec(
            name="gpaq_activity",
            description="GPAQ 신체활동 문진.",
            example_input='{"patient_id": "pt-001"}',
            fn=gpaq_activity,
        ),
        "sleep_chronotype": ToolSpec(
            name="sleep_chronotype",
            description="수면·교대근무 평가.",
            example_input='{"patient_id": "pt-001"}',
            fn=sleep_chronotype,
        ),
        "motivation_readiness": ToolSpec(
            name="motivation_readiness",
            description="변화단계(TTM) 평가. domain: diet|activity|medication",
            example_input='{"patient_id": "pt-001", "domain": "diet"}',
            fn=motivation_readiness,
        ),
        "cvd_risk_calc": ToolSpec(
            name="cvd_risk_calc",
            description="ASCVD 10년 위험도 계산.",
            example_input='{"patient_id": "pt-001"}',
            fn=cvd_risk_calc,
        ),
        "medication_propose": ToolSpec(
            name="medication_propose",
            description="1차 약물 제안. FHIR MedicationRequest 생성.",
            example_input='{"patient_id": "pt-001"}',
            fn=medication_propose,
        ),
        "meal_plan_tailored": ToolSpec(
            name="meal_plan_tailored",
            description="환자 제약 반영 식단 설계. FHIR CarePlan.activity.",
            example_input='{"budget": "low", "shift": "night-rotation"}',
            fn=meal_plan_tailored,
        ),
        "goal_set": ToolSpec(
            name="goal_set",
            description="SMART 목표 설정. FHIR Goal.",
            example_input='{"target": "HbA1c<6.8", "horizon": "12w"}',
            fn=goal_set,
        ),
        "followup_schedule": ToolSpec(
            name="followup_schedule",
            description="후속 방문·검사 예약. FHIR Appointment + ServiceRequest.",
            example_input='{"interval_weeks": 12, "tests": ["HbA1c", "eGFR"]}',
            fn=followup_schedule,
        ),
    }


SYSTEM_HINT = f"""당신은 1차 진료 의료진을 보조하는 초진 에이전트입니다.

환자 프로필:
{PATIENT}

[도메인 규칙]
- 신환 T2DM — 생활습관 문진 → 위험도 평가 → 개별 맞춤 계획 → 추적 일정 순서.
- 야간 3교대 + 저예산 제약을 반드시 플랜에 반영. 교과서 "주 5회 유산소 + 3끼 균형식"은
  이 환자에게 비현실적 — 비슷한 실패 케이스가 warnings에 있는지 반드시 확인.

[재귀 분해 저장 — 매우 중요]
반드시 **여러 번** chaeshin_retain을 호출해서 계층 트리를 만드세요. 한 번만 호출하면 안 됩니다.

실행 순서:
1) 먼저 intake/stratify 도구들을 호출해서 환자 정보 수집.
2) chaeshin_retain 1번째 — **L4 루트** 저장:
   - layer="L4", depth=3, parent_case_id 없음
   - graph.nodes = [intake, stratify, plan, followup] (4개 compose 노드)
   - 반환된 case_id를 기억 (= L4_id)
3) chaeshin_retain 2번째 — **L3 "개별 맞춤 관리 계획"** 저장:
   - layer="L3", depth=2, parent_case_id=L4_id, parent_node_id="plan"
   - graph.nodes = [meal, activity, med, goals] 같은 sub-domain 4개
   - 반환된 case_id = L3_plan_id
4) chaeshin_retain 3번째 — **L2 "저예산 교대근무 식단"** 저장:
   - layer="L2", depth=1, parent_case_id=L3_plan_id, parent_node_id="meal"
   - graph.nodes = 실제 meal_plan_tailored 같은 tool 호출들
5) chaeshin_retain 4번째 — **L2 "메트포르민 시작"** 저장:
   - layer="L2", depth=1, parent_case_id=L3_plan_id, parent_node_id="med"
   - graph.nodes = medication_propose 호출 포함
6) 저장이 끝나면 Final Answer로 마무리.

[그 외]
- 각 retain은 pending으로 저장됩니다. 판정은 12주 뒤 실제 HbA1c 결과를 보고 의료진이 직접 내립니다.
- chaeshin_verdict는 **호출하지 마세요** (사용자/의료진 권한).
- retain 5번 이상 하면 충분합니다. 완성도보다 **구조가 맞는지**가 핵심."""


USER_REQUEST = (
    f"신환 T2DM 초진입니다. 환자는 {PATIENT['label']}, HbA1c {PATIENT['hba1c']}, "
    f"{PATIENT['job']} 야간 3교대, 경제적 제약 있음. 개별 맞춤 관리 계획을 설계해서 "
    f"Chaeshin에 저장해주세요. L4 루트부터 주요 L3/L2/L1까지 재귀적으로 연결해서 저장하세요."
)


async def main():
    adapter = build_adapter()
    store, events, tmp = build_store(session_id="medical-react")

    tools = {**chaeshin_tools(store, events, category="primary-care/T2DM", source="medical-react"),
             **domain_tools()}

    agent = ReActAgent(
        adapter=adapter,
        tools=tools,
        system_hint=SYSTEM_HINT,
        max_steps=30,
    )
    try:
        await agent.run(USER_REQUEST)
        print_store_summary(store, events)
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
