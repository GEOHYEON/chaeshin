"""
김치찌개 요리사 에이전트 — Chaeshin 프레임워크 데모.

이 예제는 CBR의 전체 사이클을 보여줍니다:

1. 사용자: "김치찌개 2인분 해줘"
2. CBR Retrieve: 유사한 레시피(Tool Graph) 검색
3. Adapt: 현재 재료/상황에 맞게 그래프 조정
4. Execute: 그래프를 따라 Tool Calling 실행
5. Replan: 예상 못한 상황(전화, 재료 부족) 시 그래프 수정
6. Retain: 성공하면 CBR에 저장

실행:
    python -m examples.cooking.chef_agent
"""

import asyncio
import json
import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from chaeshin.schema import (
    ProblemFeatures,
    Solution,
    Outcome,
    CaseMetadata,
    Case,
    ToolGraph,
    ExecutionContext,
)
from chaeshin.graph_executor import GraphExecutor
from chaeshin.case_store import CaseStore
from chaeshin.planner import GraphPlanner
from examples.cooking.tools import COOKING_TOOLS


# ═══════════════════════════════════════════════════════════════════════
# 콘솔 출력 헬퍼
# ═══════════════════════════════════════════════════════════════════════

def print_header(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_step(text: str):
    print(f"  → {text}")


def print_todo(items: list):
    """환자 TODO (여기서는 주문자 TODO) 출력."""
    icons = {
        "pending": "⬚",
        "ready": "⬚",
        "running": "🔄",
        "done": "✅",
        "failed": "❌",
        "skipped": "⏭️",
    }
    print("\n  ┌─── 조리 현황 ───────────────────────┐")
    for item in items:
        icon = icons.get(item["status"], "?")
        print(f"  │  {icon} {item['label']:<20} {item['status']:>8} │")
    print("  └──────────────────────────────────────┘\n")


# ═══════════════════════════════════════════════════════════════════════
# 콜백 함수들
# ═══════════════════════════════════════════════════════════════════════

async def on_node_start(node, ctx):
    tool = COOKING_TOOLS.get(node.tool)
    display = tool.display_name if tool else node.tool
    print_step(f"🍳 [{display}] 시작 — {node.note or node.tool}")


async def on_node_end(node, ctx, result):
    tool = COOKING_TOOLS.get(node.tool)
    display = tool.display_name if tool else node.tool

    # 결과 요약
    summary = result.get("result", result.get("message", str(result)[:50]))
    print_step(f"✅ [{display}] 완료 — {summary}")


async def on_special_action(action, ctx):
    print_step(f"⚠️  특수 액션: {action}")
    if action == "ask_user":
        print_step("   사용자에게 질문이 필요합니다.")
    elif action == "emergency_exit":
        print_step("   긴급 중단!")


async def on_patient_todo_update(items):
    print_todo(items)


async def mock_replan(graph, ctx, reason):
    """리플래닝 시뮬레이션 — 실제로는 LLM이 처리."""
    print_step(f"🤖 리플래닝 요청: {reason}")
    print_step("   (데모에서는 기존 그래프를 유지합니다)")
    return graph  # 데모에서는 그래프를 수정하지 않음


# ═══════════════════════════════════════════════════════════════════════
# 메인 시나리오
# ═══════════════════════════════════════════════════════════════════════

async def scenario_kimchi_stew():
    """시나리오: 김치찌개 2인분 만들기."""

    print_header("🍲 Chaeshin 데모 — 김치찌개 요리사")
    print('  "에이전트에게 계획을 주면 하나를 풀고,')
    print('   계획을 찾는 법을 가르치면 모두를 푼다."\n')

    # ── Step 1: CBR Case Store 초기화 ──
    print_header("Step 1: CBR 케이스 저장소 로드")

    store = CaseStore(similarity_threshold=0.5)

    cases_path = os.path.join(os.path.dirname(__file__), "cases.json")
    with open(cases_path, "r", encoding="utf-8") as f:
        store.load_json(f.read())

    print_step(f"저장된 케이스: {len(store.cases)}개")
    for c in store.cases:
        print_step(f"  - {c.metadata.case_id}: {c.problem_features.request}")

    # ── Step 2: 사용자 요청 ──
    print_header("Step 2: 사용자 요청")

    user_request = "김치찌개 2인분 해줘"
    print_step(f'사용자: "{user_request}"')

    problem = ProblemFeatures(
        request=user_request,
        category="찌개류",
        keywords=["김치", "찌개", "묵은지"],
        constraints=["매운거 OK"],
        context={
            "servings": 2,
            "available_ingredients": ["묵은지", "두부", "돼지고기", "대파", "고춧가루"],
        },
    )

    # ── Step 3: CBR Retrieve ──
    print_header("Step 3: CBR — 유사 케이스 검색")

    results = store.retrieve(problem, top_k=3)
    for case, score in results:
        print_step(f"  [{score:.3f}] {case.metadata.case_id}: {case.problem_features.request}")

    best_case = results[0][0] if results else None

    if best_case:
        print_step(f"\n  ✅ 최적 케이스 선택: {best_case.metadata.case_id}")
        print_step(f"  사용 횟수: {best_case.metadata.used_count}회, 평균 만족도: {best_case.metadata.avg_satisfaction}")
        graph = best_case.solution.tool_graph
    else:
        print_step("  ❌ 유사 케이스 없음 — LLM이 새 그래프 생성")
        # 여기서 planner.create_graph()를 호출할 수 있음
        return

    # ── Step 4: 그래프 구조 출력 ──
    print_header("Step 4: Tool Graph (레시피)")

    print("  노드:")
    for node in graph.nodes:
        tool = COOKING_TOOLS.get(node.tool)
        display = tool.display_name if tool else node.tool
        print(f"    {node.id}: [{display}] {node.note}")

    print("\n  엣지:")
    for edge in graph.edges:
        to = edge.to_node or f"({edge.action})"
        cond = f" if {edge.condition}" if edge.condition else ""
        note = f" — {edge.note}" if edge.note else ""
        print(f"    {edge.from_node} → {to}{cond}{note}")

    if graph.parallel_groups:
        print(f"\n  병렬 그룹: {graph.parallel_groups}")

    # ── Step 5: 실행 ──
    print_header("Step 5: 실행")

    executor = GraphExecutor(
        tools=COOKING_TOOLS,
        on_node_start=on_node_start,
        on_node_end=on_node_end,
        on_special_action=on_special_action,
        on_patient_todo_update=on_patient_todo_update,
        on_replan=mock_replan,
    )

    ctx = await executor.execute(
        graph=graph,
        initial_input={
            "보유재료": ["묵은지", "두부", "돼지고기", "대파", "고춧가루"],
            "사용자_알레르기": [],
        },
    )

    # ── Step 6: 결과 및 CBR Retain ──
    print_header("Step 6: 결과 & CBR 저장")

    # 실행 결과 집계
    tools_done = sum(
        1 for ns in ctx.node_states.values()
        if ns.status.value == "done"
    )
    loops = sum(ns.loop_count for ns in ctx.node_states.values())

    print_step(f"실행된 도구: {tools_done}개")
    print_step(f"루프 발생: {loops}회")
    print_step(f"그래프 수정: {ctx.graph_version - 1}회")

    if ctx.special_action:
        print_step(f"특수 액션: {ctx.special_action}")
    else:
        print_step("완료 상태: 정상 종료")

    # CBR Retain — 성공하면 저장
    new_case = Case(
        problem_features=problem,
        solution=Solution(tool_graph=graph),
        outcome=Outcome(
            success=True,
            result_summary="김치찌개 2인분 완성",
            tools_executed=tools_done,
            loops_triggered=loops,
            total_time_ms=35000,
            user_satisfaction=0.90,
        ),
        metadata=CaseMetadata(
            source="demo",
            tags=["한식", "찌개", "김치"],
        ),
    )

    case_id = store.retain_if_successful(new_case, min_satisfaction=0.7)
    if case_id:
        print_step(f"✅ CBR에 새 케이스 저장됨: {case_id}")
        print_step(f"   총 케이스: {len(store.cases)}개")
    else:
        print_step("❌ 만족도 기준 미달 — 저장하지 않음")

    # ── 실행 이력 ──
    print_header("실행 이력")
    for event in ctx.history:
        print_step(f"[{event['event']}] {event['node_id']} {event.get('data', '')}")

    print_header("🎉 완료!")
    print('  "Give an agent a plan, it solves one task.')
    print('   Teach it to retrieve plans, it solves them all."')
    print()


# ═══════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(scenario_kimchi_stew())
