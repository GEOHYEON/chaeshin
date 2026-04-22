"""cooking + ReAct + Chaeshin — OpenAI 키만 있으면 바로 돌아간다.

요리사 에이전트가 ReAct 루프로 김치찌개를 만든다. Chaeshin 메모리에서 비슷한
레시피를 먼저 찾고, 없으면 직접 설계해서 실행한 뒤 저장한다.

실행:
    export OPENAI_API_KEY=sk-...
    uv run python -m examples.cooking.react_demo

환경변수:
    OPENAI_API_KEY   — 필수
    CHAESHIN_DEMO_PERSIST=1 — 데모 결과를 실제 ~/.chaeshin/chaeshin.db 에 저장
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from chaeshin.agents.react_agent import ReActAgent, ToolSpec
from examples._react_common import (
    build_adapter,
    build_store,
    chaeshin_tools,
    print_store_summary,
)


# ─────────────────────────────────────────────────────────────────────
# 도메인 도구 — 실제 요리 대신 목업 결과 반환
# ─────────────────────────────────────────────────────────────────────


FRIDGE = {
    "묵은지": "300g",
    "돼지고기 (목살)": "200g",
    "두부": "1모",
    "대파": "1대",
    "쌀뜨물": "2컵",
    "고춧가루": "1T",
    "다진마늘": "1t",
}


def check_fridge(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"items": FRIDGE, "all_available": True}


def check_allergy(args: Dict[str, Any]) -> Dict[str, Any]:
    guests = args.get("guests", ["엄마", "아빠", "본인"])
    return {"guests": guests, "allergies": {}}


def chop(args: Dict[str, Any]) -> Dict[str, Any]:
    items = args.get("items", [])
    style = args.get("style", "깍둑썰기")
    return {"completed": True, "result": f"{', '.join(items)} {style} 완료", "time_min": 5}


def saute(args: Dict[str, Any]) -> Dict[str, Any]:
    items = args.get("items", [])
    return {"completed": True, "result": f"{', '.join(items)} 중불 5분 볶기 완료", "quality": "적당"}


def simmer(args: Dict[str, Any]) -> Dict[str, Any]:
    minutes = int(args.get("minutes", 20))
    return {"completed": True, "minutes": minutes, "result": f"{minutes}분 끓이기 완료"}


def taste(args: Dict[str, Any]) -> Dict[str, Any]:
    # 시연용 — 2번째 호출에선 OK로 넘어가도록 ReAct 루프가 판단함
    return {"taste": "OK", "hint": "간 적절, 매운맛 적절"}


def season(args: Dict[str, Any]) -> Dict[str, Any]:
    seasoning = args.get("seasoning", "소금")
    return {"completed": True, "added": seasoning}


def plate(args: Dict[str, Any]) -> Dict[str, Any]:
    return {"completed": True, "portions": int(args.get("portions", 2))}


# ─────────────────────────────────────────────────────────────────────
# Assemble + run
# ─────────────────────────────────────────────────────────────────────


def domain_tools() -> Dict[str, ToolSpec]:
    return {
        "check_fridge": ToolSpec(
            name="check_fridge",
            description="냉장고 재료 확인. 인자 없음.",
            example_input="{}",
            fn=check_fridge,
        ),
        "check_allergy": ToolSpec(
            name="check_allergy",
            description="식구 알레르기 확인.",
            example_input='{"guests": ["엄마", "아빠", "본인"]}',
            fn=check_allergy,
        ),
        "chop": ToolSpec(
            name="chop",
            description="재료 썰기.",
            example_input='{"items": ["묵은지", "돼지고기", "두부"], "style": "깍둑썰기"}',
            fn=chop,
        ),
        "saute": ToolSpec(
            name="saute",
            description="재료 볶기.",
            example_input='{"items": ["돼지고기", "묵은지"]}',
            fn=saute,
        ),
        "simmer": ToolSpec(
            name="simmer",
            description="국물 끓이기.",
            example_input='{"minutes": 20}',
            fn=simmer,
        ),
        "taste": ToolSpec(
            name="taste",
            description="간보기. taste 결과가 '싱거움'이면 season으로 재양념, 'OK'면 plate.",
            example_input="{}",
            fn=taste,
        ),
        "season": ToolSpec(
            name="season",
            description="추가 양념.",
            example_input='{"seasoning": "소금"}',
            fn=season,
        ),
        "plate": ToolSpec(
            name="plate",
            description="그릇에 담기.",
            example_input='{"portions": 2}',
            fn=plate,
        ),
    }


SYSTEM_HINT = """당신은 한식 요리사 에이전트입니다.

도메인 규칙:
- 요리 시작 전에 알레르기와 재료를 먼저 확인하세요.
- 간은 끓이고 난 뒤에 봅니다. "싱거움"이면 양념 추가 후 다시 간보기.
- 완료 후에는 담아 내보냅니다.
- chaeshin_retain 호출 시, 당신이 실제로 실행한 도구 순서를 graph.nodes/edges에
  정확히 담으세요. 저장된 케이스는 pending 상태로 들어갑니다."""


USER_REQUEST = "김치찌개 2인분 만들어줘. 식구는 엄마/아빠/나."


async def main():
    adapter = build_adapter()
    store, events, tmp = build_store(session_id="cooking-react")

    tools = {**chaeshin_tools(store, events, category="cooking", source="cooking-react"),
             **domain_tools()}

    agent = ReActAgent(
        adapter=adapter,
        tools=tools,
        system_hint=SYSTEM_HINT,
        max_steps=20,
    )
    try:
        await agent.run(USER_REQUEST)
        print_store_summary(store, events)
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
