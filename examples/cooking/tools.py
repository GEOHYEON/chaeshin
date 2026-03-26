"""
요리사 도구 정의 — 김치찌개를 만들기 위한 Tool 세트.

각 도구는 하나의 요리 동작.
"""

import json
import random
from chaeshin.schema import ToolDef, ToolParam


# ═══════════════════════════════════════════════════════════════════════
# Tool Executors (시뮬레이션)
# ═══════════════════════════════════════════════════════════════════════


async def exec_allergy_check(args: dict) -> str:
    """알레르기 체크 — 식이 제한 확인."""
    ingredients = args.get("재료목록", [])
    user_allergies = args.get("사용자_알레르기", [])

    detected = [i for i in ingredients if i in user_allergies]

    if detected:
        return json.dumps({
            "allergy_detected": True,
            "allergens": detected,
            "recommendation": f"{', '.join(detected)} 대체 재료 필요",
        }, ensure_ascii=False)

    return json.dumps({
        "allergy_detected": False,
        "message": "알레르기 문제 없음",
    }, ensure_ascii=False)


async def exec_check_ingredients(args: dict) -> str:
    """재료 확인 — 필요한 재료가 있는지 체크."""
    required = args.get("필요재료", [])
    available = args.get("보유재료", [])

    available_set = set(available)
    missing = [r for r in required if r not in available_set]

    if missing:
        return json.dumps({
            "all_available": False,
            "missing": missing,
            "suggestion": f"{', '.join(missing)} 필요. 대체 재료를 찾거나 구매하세요.",
        }, ensure_ascii=False)

    return json.dumps({
        "all_available": True,
        "message": "모든 재료 준비 완료",
    }, ensure_ascii=False)


async def exec_cut(args: dict) -> str:
    """썰기 — 재료를 자르는 동작."""
    ingredients = args.get("재료", "")
    size = args.get("크기", "적당히")
    shape = args.get("모양", "깍둑썰기")

    return json.dumps({
        "completed": True,
        "result": f"{ingredients}을(를) {size} {shape}(으)로 썰기 완료",
        "time_taken_min": 5,
    }, ensure_ascii=False)


async def exec_stir_fry(args: dict) -> str:
    """볶기 — 재료를 기름에 볶는 동작."""
    ingredients = args.get("재료", "")
    heat = args.get("불세기", "중불")
    duration = args.get("시간", "5분")
    servings = args.get("인분", 2)

    # 시뮬레이션: 가끔 불 조절 실패
    overcooked = random.random() < 0.1  # 10% 확률로 과조리

    if overcooked:
        return json.dumps({
            "completed": True,
            "result": f"{ingredients} 볶기 완료 (약간 과조리)",
            "quality": "과조리",
            "time_taken_min": int(duration.replace("분", "")) + 3,
            "anomaly": "과조리",
        }, ensure_ascii=False)

    return json.dumps({
        "completed": True,
        "result": f"{ingredients}을(를) {heat}에서 {duration} 볶기 완료",
        "quality": "적당",
        "time_taken_min": int(duration.replace("분", "")),
    }, ensure_ascii=False)


async def exec_boil(args: dict) -> str:
    """끓이기 — 물/육수에 끓이는 동작."""
    ingredients = args.get("재료", "")
    broth = args.get("육수종류", "물")
    duration = args.get("시간", "20분")

    return json.dumps({
        "completed": True,
        "result": f"{ingredients}을(를) {broth}에 {duration} 끓이기 완료",
        "quality": "적당",
        "time_taken_min": int(duration.replace("분", "")),
    }, ensure_ascii=False)


async def exec_taste(args: dict) -> str:
    """간보기 — 맛 확인."""
    check_items = args.get("체크항목", ["짠맛", "매운맛"])

    # 시뮬레이션: 30% 확률로 싱거움
    bland = random.random() < 0.3

    if bland:
        return json.dumps({
            "taste": "싱거움",
            "recommendation": "소금 또는 국간장 추가 필요",
            "details": {item: "부족" for item in check_items},
        }, ensure_ascii=False)

    return json.dumps({
        "taste": "OK",
        "recommendation": "간이 적절합니다",
        "details": {item: "적절" for item in check_items},
    }, ensure_ascii=False)


async def exec_season(args: dict) -> str:
    """양념하기 — 양념을 배합/재우는 동작."""
    ingredients = args.get("재료", "")
    seasonings = args.get("양념목록", [])
    duration = args.get("시간", "10분")

    return json.dumps({
        "completed": True,
        "result": f"{ingredients}에 {', '.join(seasonings)} 양념하기 완료",
        "time_taken_min": int(duration.replace("분", "")),
    }, ensure_ascii=False)


async def exec_grill(args: dict) -> str:
    """굽기 — 오븐/팬에 굽는 동작."""
    temperature = args.get("온도", "중불")
    duration = args.get("시간", "10분")
    method = args.get("방식", "팬")

    return json.dumps({
        "completed": True,
        "result": f"{method}에서 {temperature} {duration} 굽기 완료",
        "quality": "적당",
        "time_taken_min": int(duration.replace("분", "")),
    }, ensure_ascii=False)


async def exec_plate(args: dict) -> str:
    """담기 — 완성된 요리를 그릇에 담기."""
    dish = args.get("요리명", "요리")
    servings = args.get("인분", 2)
    garnish = args.get("고명", [])

    return json.dumps({
        "completed": True,
        "result": f"{dish} {servings}인분 담기 완료",
        "garnish": garnish,
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════
# Tool Registry
# ═══════════════════════════════════════════════════════════════════════

COOKING_TOOLS = {
    "알레르기체크": ToolDef(
        name="알레르기체크",
        description="사용자의 식이 제한 및 알레르기를 확인합니다",
        display_name="알레르기 확인",
        category="safety",
        params=[
            ToolParam("재료목록", "array", "사용할 재료 목록", items={"type": "string"}),
            ToolParam("사용자_알레르기", "array", "사용자 알레르기 목록", required=False, items={"type": "string"}),
        ],
        executor=exec_allergy_check,
    ),
    "재료확인": ToolDef(
        name="재료확인",
        description="필요한 재료가 모두 준비되었는지 확인합니다",
        display_name="재료 확인",
        category="preparation",
        params=[
            ToolParam("필요재료", "array", "필요한 재료 목록", items={"type": "string"}),
            ToolParam("보유재료", "array", "현재 보유 재료", items={"type": "string"}),
        ],
        executor=exec_check_ingredients,
    ),
    "썰기": ToolDef(
        name="썰기",
        description="재료를 지정된 크기와 모양으로 자릅니다",
        display_name="재료 손질",
        category="preparation",
        params=[
            ToolParam("재료", "string", "썰 재료"),
            ToolParam("크기", "string", "크기 (큼/중간/작음)", required=False),
            ToolParam("모양", "string", "모양 (깍둑/채/어슷)", required=False),
        ],
        executor=exec_cut,
    ),
    "볶기": ToolDef(
        name="볶기",
        description="재료를 기름에 볶습니다. 불세기와 시간을 조절할 수 있습니다",
        display_name="볶기",
        category="cooking",
        params=[
            ToolParam("재료", "string", "볶을 재료"),
            ToolParam("인분", "number", "인분 수", required=False),
            ToolParam("불세기", "string", "불세기 (약/중/강)", required=False),
            ToolParam("시간", "string", "조리 시간", required=False),
        ],
        executor=exec_stir_fry,
    ),
    "끓이기": ToolDef(
        name="끓이기",
        description="재료를 물이나 육수에 끓입니다",
        display_name="끓이기",
        category="cooking",
        params=[
            ToolParam("재료", "string", "끓일 재료"),
            ToolParam("육수종류", "string", "육수 종류 (물/쌀뜨물/멸치육수)", required=False),
            ToolParam("시간", "string", "끓이는 시간", required=False),
        ],
        executor=exec_boil,
    ),
    "간보기": ToolDef(
        name="간보기",
        description="현재 요리의 맛을 확인합니다",
        display_name="간보기",
        category="quality",
        params=[
            ToolParam("체크항목", "array", "확인할 맛 요소", required=False, items={"type": "string"}),
        ],
        executor=exec_taste,
    ),
    "양념하기": ToolDef(
        name="양념하기",
        description="재료에 양념을 배합하거나 재웁니다",
        display_name="양념하기",
        category="cooking",
        params=[
            ToolParam("재료", "string", "양념할 재료"),
            ToolParam("양념목록", "array", "사용할 양념들", items={"type": "string"}),
            ToolParam("시간", "string", "재우는 시간", required=False),
        ],
        executor=exec_season,
    ),
    "굽기": ToolDef(
        name="굽기",
        description="재료를 오븐이나 팬에 굽습니다",
        display_name="굽기",
        category="cooking",
        params=[
            ToolParam("온도", "string", "조리 온도"),
            ToolParam("시간", "string", "조리 시간"),
            ToolParam("방식", "string", "조리 방식 (오븐/팬/직화)", required=False),
        ],
        executor=exec_grill,
    ),
    "담기": ToolDef(
        name="담기",
        description="완성된 요리를 그릇에 담습니다",
        display_name="완성 & 담기",
        category="finishing",
        params=[
            ToolParam("요리명", "string", "요리 이름"),
            ToolParam("인분", "number", "인분 수"),
            ToolParam("고명", "array", "올릴 고명", required=False, items={"type": "string"}),
        ],
        executor=exec_plate,
    ),
}
