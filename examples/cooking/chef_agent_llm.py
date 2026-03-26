"""
김치찌개 요리사 에이전트 — LLM + VectorDB 통합 데모.

기본 chef_agent.py와 다른 점:
- OpenAI LLM으로 그래프 생성/적응/리플래닝
- ChromaDB로 벡터 기반 유사도 검색
- 실제 LLM이 상황 판단 + 그래프 수정

실행:
    # .env에 OPENAI_API_KEY 설정 후
    python -m examples.cooking.chef_agent_llm

    # 또는 직접 키 전달
    OPENAI_API_KEY=sk-... python -m examples.cooking.chef_agent_llm
"""

import asyncio
import json
import os
import sys
import shutil

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# .env 파일 로드 (선택)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from chaeshin.schema import (
    ProblemFeatures,
    Solution,
    Outcome,
    CaseMetadata,
    Case,
)
from chaeshin.graph_executor import GraphExecutor
from chaeshin.planner import GraphPlanner
from chaeshin.case_store import CaseStore
from chaeshin.integrations.openai import OpenAIAdapter
from examples.cooking.tools import COOKING_TOOLS

# ChromaDB는 선택 — 없으면 in-memory CaseStore + OpenAI 임베딩으로 fallback
try:
    from chaeshin.integrations.chroma import ChromaCaseStore
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


# ═══════════════════════════════════════════════════════════════════════
# 설정
# ═══════════════════════════════════════════════════════════════════════

LLM_MODEL = os.getenv("CHAESHIN_LLM_MODEL", "gpt-4o-mini")
EMBEDDING_MODEL = os.getenv("CHAESHIN_EMBEDDING_MODEL", "text-embedding-3-small")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), ".chroma_data")

# 실행 시뮬레이션 딜레이 (초) — 각 도구 실행 사이 대기 시간
STEP_DELAY = float(os.getenv("CHAESHIN_STEP_DELAY", "1.0"))

# structlog 데모 모드 — 불필요한 로그 숨기기
import logging
import structlog

logging.getLogger("chaeshin").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)

# structlog의 자체 출력도 억제
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)


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
    await asyncio.sleep(STEP_DELAY * 0.3)  # 시작 시 짧은 딜레이


async def on_node_end(node, ctx, result):
    tool = COOKING_TOOLS.get(node.tool)
    display = tool.display_name if tool else node.tool
    summary = result.get("result", result.get("message", str(result)[:50]))
    await asyncio.sleep(STEP_DELAY * 0.7)  # 실행 시뮬레이션 딜레이
    print_step(f"✅ [{display}] 완료 — {summary}")


async def on_special_action(action, ctx):
    print_step(f"⚠️  특수 액션: {action}")


async def on_patient_todo_update(items):
    print_todo(items)


# ═══════════════════════════════════════════════════════════════════════
# 메인 시나리오
# ═══════════════════════════════════════════════════════════════════════

async def scenario_with_llm():
    """시나리오: LLM + VectorDB로 김치찌개 2인분 만들기."""

    print_header("🍲 Chaeshin 데모 — LLM + VectorDB 모드")
    print('  OpenAI LLM + 벡터 검색 통합\n')

    # ── 의존성 체크 ──
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("  ❌ OPENAI_API_KEY가 설정되지 않았습니다.")
        print()
        print("  방법 1: .env 파일")
        print("    echo 'OPENAI_API_KEY=sk-...' > .env")
        print()
        print("  방법 2: 환경변수")
        print("    OPENAI_API_KEY=sk-... python -m examples.cooking.chef_agent_llm")
        print()
        return

    # ── Step 1: OpenAI 어댑터 초기화 ──
    print_header("Step 1: OpenAI + VectorDB 초기화")

    adapter = OpenAIAdapter(
        model=LLM_MODEL,
        embedding_model=EMBEDDING_MODEL,
        api_key=api_key,
    )
    print_step(f"LLM: {LLM_MODEL}")
    print_step(f"Embedding: {EMBEDDING_MODEL}")

    # 케이스 저장소 초기화 — ChromaDB 우선, 없으면 in-memory fallback
    if HAS_CHROMA:
        store = ChromaCaseStore(
            embed_fn=adapter.embed_fn,
            persist_dir=CHROMA_DIR,
            similarity_threshold=0.5,
        )
        print_step(f"VectorDB: ChromaDB ({CHROMA_DIR})")

        if store.count() == 0:
            cases_path = os.path.join(os.path.dirname(__file__), "cases.json")
            with open(cases_path, "r", encoding="utf-8") as f:
                print_step("케이스 JSON → ChromaDB 임베딩 중...")
                store.load_json(f.read())
            print_step(f"✅ {store.count()}개 케이스 로드 + 임베딩 완료")
        else:
            cases_path = os.path.join(os.path.dirname(__file__), "cases.json")
            with open(cases_path, "r", encoding="utf-8") as f:
                store.load_json(f.read())
            print_step(f"✅ ChromaDB에서 {store.count()}개 케이스 로드")

        print_step(f"저장소 통계: {store.stats()}")
    else:
        print_step("⚠️  ChromaDB 없음 — in-memory 임베딩 검색 모드")
        print_step("   (pip install chromadb 로 설치하면 영구 저장 가능)")
        store = CaseStore(
            embed_fn=adapter.embed_fn,
            similarity_threshold=0.5,
        )
        cases_path = os.path.join(os.path.dirname(__file__), "cases.json")
        with open(cases_path, "r", encoding="utf-8") as f:
            print_step("케이스 JSON → 임베딩 중...")
            store.load_json(f.read())
        print_step(f"✅ {len(store.cases)}개 케이스 로드 + 임베딩 완료")

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

    # ── Step 3: CBR Retrieve (벡터 검색) ──
    print_header("Step 3: CBR — 벡터 유사도 검색 (ChromaDB)")

    results = store.retrieve(problem, top_k=3)
    for case, score in results:
        print_step(f"[{score:.3f}] {case.metadata.case_id}: {case.problem_features.request}")

    best_case = results[0][0] if results else None
    best_score = results[0][1] if results else 0

    if best_case and best_score >= store.similarity_threshold:
        print_step(f"\n✅ 최적 케이스: {best_case.metadata.case_id} (유사도: {best_score:.3f})")
        graph = best_case.solution.tool_graph
    else:
        # 유사 케이스 없음 → LLM이 새 그래프 생성
        print_step("❌ 유사 케이스 없음 → LLM이 새 그래프를 생성합니다")
        planner = GraphPlanner(
            llm_fn=adapter.llm_fn,
            tools=COOKING_TOOLS,
        )
        print_step("🤖 LLM에 그래프 생성 요청 중...")
        graph = await planner.create_graph(problem)
        print_step(f"✅ LLM이 {len(graph.nodes)}개 노드, {len(graph.edges)}개 엣지 그래프 생성")

    # ── Step 4: LLM Adapt (필요 시) ──
    print_header("Step 4: LLM Adapt — 현재 상황에 맞게 그래프 조정")

    planner = GraphPlanner(
        llm_fn=adapter.llm_fn,
        tools=COOKING_TOOLS,
    )

    if best_case:
        print_step("🤖 LLM에 그래프 적응 요청 중...")
        adapted_graph = await planner.adapt_graph(best_case, problem)

        if adapted_graph != graph:
            print_step("✅ 그래프가 현재 상황에 맞게 수정됨")
            graph = adapted_graph
        else:
            print_step("✅ 기존 그래프가 그대로 사용 가능 (차이 없음)")

    # ── Step 5: 그래프 구조 출력 ──
    print_header("Step 5: Tool Graph (레시피)")

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

    # ── Step 6: 실행 (LLM 리플래닝 포함) ──
    print_header("Step 6: 실행 (예외 시 LLM 리플래닝)")

    async def llm_replan(g, ctx, reason):
        """LLM 기반 리플래닝."""
        print_step(f"🤖 리플래닝 요청: {reason}")
        print_step("   LLM이 그래프를 수정합니다...")
        new_graph = await planner.replan_graph(g, ctx, reason)
        if new_graph != g:
            added = len(new_graph.nodes) - len(g.nodes)
            print_step(f"   ✅ 그래프 수정 완료 (노드 변화: {added:+d})")
        else:
            print_step("   ℹ️  LLM이 기존 그래프를 유지하기로 결정")
        return new_graph

    executor = GraphExecutor(
        tools=COOKING_TOOLS,
        on_node_start=on_node_start,
        on_node_end=on_node_end,
        on_special_action=on_special_action,
        on_patient_todo_update=on_patient_todo_update,
        on_replan=llm_replan,
    )

    ctx = await executor.execute(
        graph=graph,
        initial_input={
            "보유재료": ["묵은지", "두부", "돼지고기", "대파", "고춧가루"],
            "사용자_알레르기": [],
        },
    )

    # ── Step 7: 결과 및 CBR Retain ──
    print_header("Step 7: 결과 & CBR Retain (ChromaDB에 저장)")

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

    # CBR Retain — 저장소에 저장
    new_case = Case(
        problem_features=problem,
        solution=Solution(tool_graph=graph),
        outcome=Outcome(
            success=True,
            result_summary="김치찌개 2인분 완성 (LLM 모드)",
            tools_executed=tools_done,
            loops_triggered=loops,
            total_time_ms=35000,
            user_satisfaction=0.90,
        ),
        metadata=CaseMetadata(
            source="llm_demo",
            tags=["한식", "찌개", "김치", "llm"],
        ),
    )

    case_id = store.retain_if_successful(new_case, min_satisfaction=0.7)
    if case_id:
        total = store.count() if hasattr(store, "count") else len(store.cases)
        print_step(f"✅ 케이스 저장 완료: {case_id}")
        print_step(f"   총 케이스: {total}개")
    else:
        print_step("❌ 만족도 기준 미달 — 저장하지 않음")

    # ── 실행 이력 ──
    print_header("실행 이력")
    for event in ctx.history:
        print_step(f"[{event['event']}] {event['node_id']} {event.get('data', '')}")

    # ── 저장소 최종 통계 ──
    print_header("저장소 통계")
    if hasattr(store, "stats"):
        stats = store.stats()
        for k, v in stats.items():
            print_step(f"{k}: {v}")
    else:
        print_step(f"총 케이스: {len(store.cases)}개")
        print_step(f"모드: in-memory (OpenAI 임베딩)")

    print_header("🎉 완료!")
    print('  LLM + VectorDB 통합 CBR 사이클이 성공적으로 실행되었습니다.')
    print('  다음 실행에서는 ChromaDB에 저장된 케이스를 재활용합니다.')
    print()


async def scenario_new_dish():
    """시나리오 2: CBR에 없는 새로운 요리 — LLM이 처음부터 그래프 생성."""

    print_header("🍳 시나리오 2 — 새로운 요리 (CBR에 없는 케이스)")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("  ❌ OPENAI_API_KEY 필요")
        return

    adapter = OpenAIAdapter(model=LLM_MODEL, api_key=api_key)

    if HAS_CHROMA:
        store = ChromaCaseStore(
            embed_fn=adapter.embed_fn,
            persist_dir=CHROMA_DIR,
            similarity_threshold=0.8,
        )
    else:
        store = CaseStore(
            embed_fn=adapter.embed_fn,
            similarity_threshold=0.8,
        )

    # 기존 케이스 로드
    cases_path = os.path.join(os.path.dirname(__file__), "cases.json")
    with open(cases_path, "r", encoding="utf-8") as f:
        store.load_json(f.read())

    # 찌개와 전혀 다른 요리 요청
    problem = ProblemFeatures(
        request="치즈 오믈렛 만들어줘",
        category="양식",
        keywords=["오믈렛", "계란", "치즈", "아침식사"],
        constraints=["5분 이내", "간단하게"],
        context={
            "servings": 1,
            "available_ingredients": ["계란", "치즈", "버터", "소금", "후추"],
        },
    )

    print_step(f'사용자: "{problem.request}"')

    # CBR 검색 — 유사 케이스 없을 가능성 높음
    results = store.retrieve(problem, top_k=1)
    if results:
        print_step(f"가장 유사한 케이스: {results[0][0].metadata.case_id} (유사도: {results[0][1]:.3f})")

    best = store.retrieve_best(problem)

    if best is None:
        print_step("❌ 유사 케이스 없음 — LLM이 새 그래프를 생성합니다\n")

        planner = GraphPlanner(llm_fn=adapter.llm_fn, tools=COOKING_TOOLS)
        print_step("🤖 LLM에 그래프 생성 요청 중...")
        graph = await planner.create_graph(problem)

        print_step(f"✅ LLM이 생성한 그래프:")
        print(f"\n  노드 ({len(graph.nodes)}개):")
        for node in graph.nodes:
            print(f"    {node.id}: [{node.tool}] {node.note}")
        print(f"\n  엣지 ({len(graph.edges)}개):")
        for edge in graph.edges:
            to = edge.to_node or f"({edge.action})"
            cond = f" if {edge.condition}" if edge.condition else ""
            print(f"    {edge.from_node} → {to}{cond}")

        # 실행
        print_step("\n🍳 실행 시작...")

        async def llm_replan(g, ctx, reason):
            print_step(f"🤖 리플래닝: {reason}")
            new_g = await planner.replan_graph(g, ctx, reason)
            return new_g

        executor = GraphExecutor(
            tools=COOKING_TOOLS,
            on_node_start=on_node_start,
            on_node_end=on_node_end,
            on_replan=llm_replan,
        )

        ctx = await executor.execute(
            graph=graph,
            initial_input={
                "보유재료": ["계란", "치즈", "버터", "소금", "후추"],
                "사용자_알레르기": [],
            },
        )

        tools_done = sum(
            1 for ns in ctx.node_states.values()
            if ns.status.value == "done"
        )

        print_step(f"\n✅ 실행 완료 — 도구 {tools_done}개 실행")

        # 저장
        new_case = Case(
            problem_features=problem,
            solution=Solution(tool_graph=graph),
            outcome=Outcome(
                success=True,
                result_summary="치즈 오믈렛 완성 (LLM 생성)",
                tools_executed=tools_done,
                user_satisfaction=0.85,
            ),
            metadata=CaseMetadata(
                source="llm_created",
                tags=["양식", "오믈렛", "아침", "llm_generated"],
            ),
        )
        store.retain(new_case)
        print_step(f"✅ 새 케이스가 ChromaDB에 저장됨 — 다음엔 검색 가능!")
    else:
        print_step(f"✅ 유사 케이스 발견: {best.metadata.case_id}")
        print_step("   기존 그래프를 적응합니다.")


def cleanup_chroma():
    """ChromaDB 데이터 초기화."""
    if os.path.exists(CHROMA_DIR):
        shutil.rmtree(CHROMA_DIR)
        print(f"  → ChromaDB 데이터 삭제: {CHROMA_DIR}")


# ═══════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════

def main():
    global LLM_MODEL

    import argparse

    parser = argparse.ArgumentParser(
        description="Chaeshin 요리사 에이전트 — LLM + VectorDB 모드"
    )
    parser.add_argument(
        "--scenario",
        choices=["kimchi", "new", "both"],
        default="kimchi",
        help="실행할 시나리오 (kimchi: 김치찌개, new: 새 요리, both: 둘 다)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="ChromaDB 데이터 초기화 후 실행",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"LLM 모델 (기본: {LLM_MODEL})",
    )
    args = parser.parse_args()

    if args.model:
        LLM_MODEL = args.model

    if args.reset:
        cleanup_chroma()

    if args.scenario in ("kimchi", "both"):
        asyncio.run(scenario_with_llm())

    if args.scenario in ("new", "both"):
        asyncio.run(scenario_new_dish())


if __name__ == "__main__":
    main()
