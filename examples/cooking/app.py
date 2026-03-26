"""
채신 (Chaeshin) 요리사 에이전트 — Gradio 웹 데모.

CBR(Case-Based Reasoning) 기반 Tool Calling 프레임워크의 전체 사이클을
웹 UI로 시각화합니다.

실행:
    uv run python -m examples.cooking.app

    # 또는
    python -m examples.cooking.app
"""

import asyncio
import json
import os
import sys
import shutil
import time
from typing import Optional

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# .env 파일 로드 (선택)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# structlog 노이즈 억제
import logging
import structlog

logging.getLogger("chaeshin").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
)

import gradio as gr

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

# ChromaDB는 선택
try:
    from chaeshin.integrations.chroma import ChromaCaseStore
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

CHROMA_DIR = os.path.join(os.path.dirname(__file__), ".chroma_data")
CASES_PATH = os.path.join(os.path.dirname(__file__), "cases.json")
STEP_DELAY = float(os.getenv("CHAESHIN_STEP_DELAY", "0.8"))


# ═══════════════════════════════════════════════════════════════════════
# 헬퍼 함수
# ═══════════════════════════════════════════════════════════════════════

def format_graph_text(graph) -> str:
    """Tool Graph를 사람이 읽기 좋은 텍스트로 변환."""
    lines = []
    lines.append("📋 **노드 (도구 실행 단계)**")
    for node in graph.nodes:
        tool = COOKING_TOOLS.get(node.tool)
        display = tool.display_name if tool else node.tool
        lines.append(f"  • `{node.id}` → **{display}** — {node.note or node.tool}")

    lines.append("")
    lines.append("🔗 **엣지 (실행 흐름)**")
    for edge in graph.edges:
        to = edge.to_node or f"({edge.action})"
        cond = f"  `if {edge.condition}`" if edge.condition else ""
        note = f" — {edge.note}" if edge.note else ""
        lines.append(f"  • `{edge.from_node}` → `{to}`{cond}{note}")

    if graph.parallel_groups:
        lines.append("")
        lines.append(f"⚡ **병렬 그룹**: {graph.parallel_groups}")

    return "\n".join(lines)


def format_graph_mermaid(graph) -> str:
    """Tool Graph를 Mermaid 다이어그램으로 변환."""
    lines = ["graph TD"]
    for node in graph.nodes:
        tool = COOKING_TOOLS.get(node.tool)
        display = tool.display_name if tool else node.tool
        label = f"{display}"
        if node.note:
            label += f"<br/>{node.note}"
        lines.append(f'    {node.id}["{label}"]')

    for edge in graph.edges:
        if edge.to_node:
            if edge.condition:
                lines.append(f"    {edge.from_node} -->|{edge.condition}| {edge.to_node}")
            else:
                lines.append(f"    {edge.from_node} --> {edge.to_node}")
        else:
            action_id = f"action_{edge.from_node}"
            lines.append(f'    {action_id}(("{edge.action}"))')
            lines.append(f"    {edge.from_node} --> {action_id}")

    return "\n".join(lines)


def build_status_table(items: list) -> str:
    """실행 현황을 마크다운 테이블로."""
    icons = {
        "pending": "⬜",
        "ready": "🔲",
        "running": "🔄",
        "done": "✅",
        "failed": "❌",
        "skipped": "⏭️",
    }
    rows = ["| 상태 | 단계 |", "|:---:|:---|"]
    for item in items:
        icon = icons.get(item["status"], "❓")
        rows.append(f"| {icon} | {item['label']} |")
    return "\n".join(rows)


# ═══════════════════════════════════════════════════════════════════════
# 핵심 파이프라인
# ═══════════════════════════════════════════════════════════════════════

async def run_pipeline(
    api_key: str,
    model: str,
    embedding_model: str,
    user_request: str,
    category: str,
    keywords: str,
    constraints: str,
    ingredients: str,
    allergies: str,
    servings: int,
):
    """CBR 전체 파이프라인을 실행하면서 단계별 로그를 yield."""

    log_lines = []

    def log(msg: str):
        log_lines.append(msg)
        return "\n".join(log_lines)

    # ── 유효성 검사 ──
    if not api_key or not api_key.strip():
        yield log("❌ **OpenAI API Key**를 입력해주세요."), "", ""
        return

    if not user_request.strip():
        yield log("❌ **요리 요청**을 입력해주세요."), "", ""
        return

    api_key = api_key.strip()

    # ── Step 1: 초기화 ──
    yield log("## Step 1: 초기화\n"), "", ""
    await asyncio.sleep(0.3)

    adapter = OpenAIAdapter(
        model=model,
        embedding_model=embedding_model,
        api_key=api_key,
    )
    yield log(f"✅ LLM: `{model}` / Embedding: `{embedding_model}`"), "", ""

    # 케이스 저장소
    if HAS_CHROMA:
        store = ChromaCaseStore(
            embed_fn=adapter.embed_fn,
            persist_dir=CHROMA_DIR,
            similarity_threshold=0.5,
        )
        with open(CASES_PATH, "r", encoding="utf-8") as f:
            store.load_json(f.read())
        yield log(f"✅ VectorDB: ChromaDB — {store.count()}개 케이스 로드"), "", ""
    else:
        store = CaseStore(
            embed_fn=adapter.embed_fn,
            similarity_threshold=0.5,
        )
        with open(CASES_PATH, "r", encoding="utf-8") as f:
            store.load_json(f.read())
        yield log(f"✅ In-memory 저장소 — {len(store.cases)}개 케이스 로드"), "", ""

    await asyncio.sleep(0.3)

    # ── Step 2: 사용자 요청 파싱 ──
    yield log(f"\n## Step 2: 사용자 요청\n\n> **\"{user_request}\"**"), "", ""
    await asyncio.sleep(0.3)

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    const_list = [c.strip() for c in constraints.split(",") if c.strip()]
    ingr_list = [i.strip() for i in ingredients.split(",") if i.strip()]
    allergy_list = [a.strip() for a in allergies.split(",") if a.strip()]

    problem = ProblemFeatures(
        request=user_request,
        category=category,
        keywords=kw_list,
        constraints=const_list,
        context={
            "servings": servings,
            "available_ingredients": ingr_list,
        },
    )

    # ── Step 3: CBR Retrieve ──
    yield log("\n## Step 3: CBR — 유사 케이스 검색\n"), "", ""
    await asyncio.sleep(0.3)

    try:
        results = store.retrieve(problem, top_k=3)
    except Exception as e:
        yield log(f"❌ 검색 오류: {e}"), "", ""
        return

    if results:
        for case, score in results:
            yield log(f"  • `[{score:.3f}]` {case.metadata.case_id}: {case.problem_features.request}"), "", ""
            await asyncio.sleep(0.2)

    best_case = results[0][0] if results else None
    best_score = results[0][1] if results else 0

    graph = None
    planner = GraphPlanner(llm_fn=adapter.llm_fn, tools=COOKING_TOOLS)

    if best_case and best_score >= store.similarity_threshold:
        yield log(f"\n✅ **최적 케이스**: `{best_case.metadata.case_id}` (유사도: {best_score:.3f})"), "", ""
        graph = best_case.solution.tool_graph
    else:
        yield log("\n⚠️ 유사 케이스 없음 → **LLM이 새 그래프를 생성합니다**"), "", ""
        await asyncio.sleep(0.3)
        yield log("🤖 LLM에 그래프 생성 요청 중..."), "", ""
        try:
            graph = await planner.create_graph(problem)
            yield log(f"✅ LLM이 **{len(graph.nodes)}개 노드**, **{len(graph.edges)}개 엣지** 그래프 생성"), "", ""
        except Exception as e:
            yield log(f"❌ 그래프 생성 실패: {e}"), "", ""
            return

    # ── Step 4: LLM Adapt ──
    yield log("\n## Step 4: LLM Adapt — 상황 맞춤 조정\n"), "", ""
    await asyncio.sleep(0.3)

    if best_case:
        yield log("🤖 LLM에 그래프 적응 요청 중..."), "", ""
        try:
            adapted_graph = await planner.adapt_graph(best_case, problem)
            if adapted_graph != graph:
                graph = adapted_graph
                yield log("✅ 그래프가 현재 상황에 맞게 **수정됨**"), "", ""
            else:
                yield log("✅ 기존 그래프 **그대로 사용** 가능"), "", ""
        except Exception as e:
            yield log(f"⚠️ Adapt 실패 (기존 그래프 사용): {e}"), "", ""
    else:
        yield log("ℹ️ 새로 생성된 그래프 — Adapt 스킵"), "", ""

    # ── Step 5: 그래프 구조 표시 ──
    graph_text = format_graph_text(graph)
    graph_mermaid = format_graph_mermaid(graph)

    yield log(f"\n## Step 5: Tool Graph (레시피)\n\n{graph_text}"), graph_mermaid, ""
    await asyncio.sleep(0.5)

    # ── Step 6: 실행 ──
    yield log("\n## Step 6: 실행\n"), graph_mermaid, ""
    await asyncio.sleep(0.3)

    status_md = ""

    async def on_node_start(node, ctx):
        nonlocal status_md
        tool = COOKING_TOOLS.get(node.tool)
        display = tool.display_name if tool else node.tool
        log(f"🍳 **[{display}]** 시작 — {node.note or node.tool}")
        await asyncio.sleep(STEP_DELAY * 0.3)

    async def on_node_end(node, ctx, result):
        nonlocal status_md
        tool = COOKING_TOOLS.get(node.tool)
        display = tool.display_name if tool else node.tool
        summary = result.get("result", result.get("message", str(result)[:50]))
        await asyncio.sleep(STEP_DELAY * 0.7)
        log(f"✅ **[{display}]** 완료 — {summary}")

    async def on_special_action(action, ctx):
        log(f"⚠️ **특수 액션**: {action}")

    async def on_todo_update(items):
        nonlocal status_md
        status_md = build_status_table(items)

    async def llm_replan(g, ctx, reason):
        log(f"🤖 **리플래닝**: {reason}")
        try:
            new_graph = await planner.replan_graph(g, ctx, reason)
            if new_graph != g:
                added = len(new_graph.nodes) - len(g.nodes)
                log(f"✅ 그래프 수정 완료 (노드 변화: {added:+d})")
            else:
                log("ℹ️ LLM이 기존 그래프 유지")
            return new_graph
        except Exception as e:
            log(f"⚠️ 리플래닝 실패: {e}")
            return g

    executor = GraphExecutor(
        tools=COOKING_TOOLS,
        on_node_start=on_node_start,
        on_node_end=on_node_end,
        on_special_action=on_special_action,
        on_patient_todo_update=on_todo_update,
        on_replan=llm_replan,
    )

    # 실행은 콜백에서 log()를 호출하므로, 별도 태스크로 실행하고
    # 주기적으로 log_lines를 yield
    exec_task = asyncio.create_task(
        executor.execute(
            graph=graph,
            initial_input={
                "보유재료": ingr_list,
                "사용자_알레르기": allergy_list,
            },
        )
    )

    # 실행 중 로그 스트리밍
    prev_len = len(log_lines)
    while not exec_task.done():
        await asyncio.sleep(0.3)
        if len(log_lines) > prev_len:
            prev_len = len(log_lines)
            yield "\n".join(log_lines), graph_mermaid, status_md

    # 실행 완료
    try:
        ctx = exec_task.result()
    except Exception as e:
        yield log(f"\n❌ 실행 오류: {e}"), graph_mermaid, status_md
        return

    # ── Step 7: 결과 & Retain ──
    tools_done = sum(
        1 for ns in ctx.node_states.values()
        if ns.status.value == "done"
    )
    loops = sum(ns.loop_count for ns in ctx.node_states.values())

    log(f"\n## Step 7: 결과 & CBR Retain\n")
    log(f"  • 실행된 도구: **{tools_done}개**")
    log(f"  • 루프 발생: **{loops}회**")
    log(f"  • 그래프 수정: **{ctx.graph_version - 1}회**")

    if ctx.special_action:
        log(f"  • 특수 액션: {ctx.special_action}")
    else:
        log(f"  • 완료 상태: ✅ 정상 종료")

    # CBR Retain
    new_case = Case(
        problem_features=problem,
        solution=Solution(tool_graph=graph),
        outcome=Outcome(
            success=True,
            result_summary=f"{user_request} 완성 (LLM 모드)",
            tools_executed=tools_done,
            loops_triggered=loops,
            total_time_ms=35000,
            user_satisfaction=0.90,
        ),
        metadata=CaseMetadata(
            source="gradio_demo",
            tags=kw_list + ["gradio"],
        ),
    )

    case_id = store.retain_if_successful(new_case, min_satisfaction=0.7)
    if case_id:
        total = store.count() if hasattr(store, "count") else len(store.cases)
        log(f"\n✅ 케이스 저장 완료: `{case_id}` (총 {total}개)")
    else:
        log("\n❌ 만족도 기준 미달 — 저장하지 않음")

    log("\n---\n🎉 **완료!** CBR 사이클이 성공적으로 실행되었습니다.")

    yield "\n".join(log_lines), graph_mermaid, status_md


def run_pipeline_sync(*args):
    """Gradio에서 generator로 yield하기 위한 동기 래퍼."""
    loop = asyncio.new_event_loop()

    async def collect():
        results = []
        async for item in run_pipeline(*args):
            results.append(item)
        return results

    all_results = loop.run_until_complete(collect())
    loop.close()

    for result in all_results:
        yield result


def reset_chroma():
    """ChromaDB 데이터 초기화."""
    if os.path.exists(CHROMA_DIR):
        shutil.rmtree(CHROMA_DIR)
        return "✅ ChromaDB 데이터가 초기화되었습니다."
    return "ℹ️ 초기화할 ChromaDB 데이터가 없습니다."


# ═══════════════════════════════════════════════════════════════════════
# Gradio UI
# ═══════════════════════════════════════════════════════════════════════

def create_app() -> gr.Blocks:
    with gr.Blocks(
        title="채신 (Chaeshin) — 요리사 에이전트 데모",
        theme=gr.themes.Soft(),
        css="""
        .main-header { text-align: center; margin-bottom: 1rem; }
        .main-header h1 { font-size: 2rem; margin-bottom: 0.3rem; }
        .main-header p { color: #666; font-size: 0.95rem; }
        """,
    ) as app:
        gr.HTML("""
        <div class="main-header">
            <h1>🍲 채신 (Chaeshin) 採薪</h1>
            <p>CBR 기반 Tool Calling 프레임워크 — 요리사 에이전트 데모</p>
            <p style="font-size: 0.8rem; color: #999;">
                Retrieve → Adapt → Execute → Retain
            </p>
        </div>
        """)

        with gr.Row():
            # ── 왼쪽: 설정 + 입력 ──
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ 설정")
                api_key = gr.Textbox(
                    label="OpenAI API Key",
                    type="password",
                    placeholder="sk-...",
                    value=os.getenv("OPENAI_API_KEY", ""),
                )
                with gr.Row():
                    model = gr.Dropdown(
                        label="LLM 모델",
                        choices=["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
                        value=os.getenv("CHAESHIN_LLM_MODEL", "gpt-4o-mini"),
                    )
                    embed_model = gr.Dropdown(
                        label="임베딩 모델",
                        choices=["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
                        value=os.getenv("CHAESHIN_EMBEDDING_MODEL", "text-embedding-3-small"),
                    )

                gr.Markdown("### 🍳 요리 요청")
                user_request = gr.Textbox(
                    label="무엇을 만들까요?",
                    placeholder="예: 김치찌개 2인분 해줘",
                    value="김치찌개 2인분 해줘",
                    lines=2,
                )
                with gr.Row():
                    category = gr.Textbox(
                        label="카테고리",
                        value="찌개류",
                        scale=1,
                    )
                    servings = gr.Number(
                        label="인분",
                        value=2,
                        minimum=1,
                        maximum=10,
                        step=1,
                        scale=1,
                    )
                keywords = gr.Textbox(
                    label="키워드 (쉼표 구분)",
                    value="김치, 찌개, 묵은지",
                    placeholder="김치, 찌개, 묵은지",
                )
                ingredients = gr.Textbox(
                    label="보유 재료 (쉼표 구분)",
                    value="묵은지, 두부, 돼지고기, 대파, 고춧가루",
                    placeholder="묵은지, 두부, 돼지고기, 대파, 고춧가루",
                )
                with gr.Row():
                    constraints = gr.Textbox(
                        label="제약 조건",
                        value="매운거 OK",
                        placeholder="예: 매운거 X, 30분 이내",
                        scale=2,
                    )
                    allergies = gr.Textbox(
                        label="알레르기",
                        value="",
                        placeholder="예: 땅콩, 새우",
                        scale=1,
                    )

                with gr.Row():
                    run_btn = gr.Button("🚀 실행", variant="primary", scale=3)
                    reset_btn = gr.Button("🗑️ DB 초기화", variant="secondary", scale=1)

                reset_output = gr.Textbox(label="초기화 결과", visible=True, interactive=False)

                # 프리셋 예시
                gr.Markdown("### 💡 예시")
                gr.Examples(
                    examples=[
                        ["김치찌개 2인분 해줘", "찌개류", "김치, 찌개, 묵은지", "매운거 OK", "묵은지, 두부, 돼지고기, 대파, 고춧가루", "", 2],
                        ["된장찌개 만들어줘", "찌개류", "된장, 찌개, 두부", "담백하게", "된장, 두부, 애호박, 감자, 대파", "", 2],
                        ["치즈 오믈렛 만들어줘", "양식", "오믈렛, 계란, 치즈, 아침식사", "5분 이내, 간단하게", "계란, 치즈, 버터, 소금, 후추", "", 1],
                        ["제육볶음 3인분", "볶음류", "제육, 돼지고기, 볶음", "매콤달콤", "돼지고기, 양파, 대파, 고추장, 고춧가루", "", 3],
                    ],
                    inputs=[user_request, category, keywords, constraints, ingredients, allergies, servings],
                    label="",
                )

            # ── 오른쪽: 결과 ──
            with gr.Column(scale=2):
                gr.Markdown("### 📊 실행 결과")

                with gr.Tabs():
                    with gr.Tab("📜 실행 로그"):
                        log_output = gr.Markdown(
                            value="*실행 버튼을 눌러 시작하세요.*",
                            height=600,
                        )

                    with gr.Tab("🗺️ 그래프"):
                        graph_output = gr.Code(
                            label="Mermaid 다이어그램 (mermaid.live에 붙여넣기)",
                            language=None,
                            lines=20,
                        )

                    with gr.Tab("📋 실행 현황"):
                        status_output = gr.Markdown(
                            value="*실행이 시작되면 현황이 표시됩니다.*",
                        )

        # ── 이벤트 바인딩 ──
        run_btn.click(
            fn=run_pipeline_sync,
            inputs=[
                api_key, model, embed_model,
                user_request, category, keywords,
                constraints, ingredients, allergies, servings,
            ],
            outputs=[log_output, graph_output, status_output],
        )

        reset_btn.click(
            fn=reset_chroma,
            inputs=[],
            outputs=[reset_output],
        )

    return app


# ═══════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Chaeshin 요리사 에이전트 — Gradio 웹 데모"
    )
    parser.add_argument(
        "--port", type=int, default=7860,
        help="서버 포트 (기본: 7860)",
    )
    parser.add_argument(
        "--share", action="store_true",
        help="Gradio 공유 링크 생성",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="ChromaDB 데이터 초기화 후 실행",
    )
    args = parser.parse_args()

    if args.reset:
        print(reset_chroma())

    app = create_app()
    app.launch(
        server_port=args.port,
        share=args.share,
    )


if __name__ == "__main__":
    main()
