# Quick Start

[한국어](ko/quickstart.md)

Get Chaeshin running in under 2 minutes.

## 1. Install

```bash
pip install chaeshin
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install chaeshin
```

Or from source:

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # recommended
# or: pip install -e ".[dev]"
```

## 2. Run the Legacy Rule-Based Cooking Demo

> This compatibility demo illustrates the earlier ToolGraph executor artifact. It
> is not the target ReAct runtime, where all layers are retrieved as context and
> ReAct directly chooses one next Tool. Use Section 5 for the primary path.

```bash
python -m examples.cooking.chef_agent
```

This runs a full CBR cycle — Retrieve → Execute → Retain — using a kimchi stew recipe as an example.

### What you'll see

```
============================================================
  Step 1: CBR 케이스 저장소 로드
============================================================

  → 저장된 케이스: 5개
  → - recipe_kimchi_stew_001: 김치찌개 만들어줘

============================================================
  Step 3: CBR — 유사 케이스 검색
============================================================

  → [0.850] recipe_kimchi_stew_001: 김치찌개 만들어줘
  → ✅ 최적 케이스 선택: recipe_kimchi_stew_001

============================================================
  Step 5: 실행
============================================================

  → 🍳 [알레르기 체크] 시작
  → ✅ [알레르기 체크] 완료
  → 🍳 [재료 확인] 시작
  → ✅ [재료 확인] 완료
  → 🍳 [썰기] 시작
  ...
  → ✅ [담기] 완료 — 김치찌개 2인분 완성

============================================================
  🎉 완료!
============================================================
```

The agent loads 5 stored cases, finds the best match for "김치찌개 2인분 해줘", executes each tool node in order, and saves the result back to the case store.

## 3. Understand the Legacy Flow

This legacy demo follows 6 steps:

```
User Request → Retrieve (find similar case)
             → Inspect (view the Tool Graph)
             → Execute (run tools node by node)
             → Retain (save if successful)
```

**Retrieve**: The `CaseStore` compares your request against stored cases using keyword overlap and similarity scoring. The best-matching Tool Graph is returned.

**Execute**: The `GraphExecutor` walks the graph node by node. Each node calls a tool function. Edges define the flow — including conditions ("if bland → boil again") and parallel groups.

**Retain**: If execution succeeds and satisfaction meets the threshold, the new case is saved back to the store for future retrieval.

## 4. Explore the Code

| File | What it does |
|------|-------------|
| `examples/cooking/cases.json` | 5 stored CBR cases (kimchi stew, doenjang stew, recovery scenarios) |
| `examples/cooking/tools.py` | Mock cooking tools (chop, boil, taste, etc.) |
| `examples/cooking/chef_agent.py` | Rule-based demo script |
| `examples/cooking/react_demo.py` | Primary planner-free ReAct + hybrid memory demo |
| `examples/cooking/chef_agent_llm.py` | Legacy GraphPlanner demo script |
| `examples/cooking/app.py` | Legacy GraphPlanner Gradio web UI |
| `chaeshin/case_store.py` | CBR case storage and retrieval |
| `chaeshin/graph_executor.py` | Tool Graph execution engine |
| `chaeshin/planner.py` | Lazy-loaded legacy compatibility API |
| `chaeshin/integrations/openai.py` | OpenAI LLM + embedding adapter |
| `chaeshin/integrations/chroma.py` | ChromaDB vector case store |
| `chaeshin/schema.py` | Data models (Case, ToolGraph, Edge, Node) |

## 5. Run with Planner-Free ReAct + Hybrid Memory

The primary demo uses one ReAct prompt for query profiling, reading retrieved
Procedure/ToolGraph context, next-Tool selection, adaptive requery, and actual-trace retention.
OpenAI embeddings and lexical signals are combined by `CaseStore`:

```bash
cp .env.example .env         # add your OPENAI_API_KEY
uv run python -m examples.cooking.react_demo
```

This demo:

- Seeds the five cooking Cases and creates embeddings for them
- Returns ProblemFeatures, L1 ToolGraph and L2+ Procedure structures, outcomes, and provenance evidence
- Treats retrieval rank and memory structure only as references; ReAct directly chooses the next Tool
- Uses no separate Planner and chooses one next action after each Observation
- Retains only actual domain-tool calls as a new `pending` Case

The default request is the information-only query “김치찌개 끓이는 법 알려줘”,
so it explains the retrieved procedural context without pretending that cooking tools ran.
Use an execution request such as “김치찌개 2인분 만들어줘” to exercise domain
actions and actual-trace retention.

## 6. Legacy Web UI Demo (Gradio)

This compatibility demo still uses the older GraphPlanner path:

```bash
cp .env.example .env         # add your OPENAI_API_KEY
uv run python -m examples.cooking.app
```

This opens a Gradio web app where you can:

- Enter any cooking request in natural language
- Watch the full CBR pipeline (Retrieve → Adapt → Execute → Retain) step by step
- View the generated Tool Graph
- Track execution status in real time
- Try preset examples (kimchi stew, doenjang stew, cheese omelette, etc.)

Options:

```bash
# Custom port
uv run python -m examples.cooking.app --port 8080

# Create a public share link
uv run python -m examples.cooking.app --share

# Reset ChromaDB before starting
uv run python -m examples.cooking.app --reset
```

## 7. Next Steps

**Add your own case**: Edit `examples/cooking/cases.json` to add a new recipe. Follow the existing structure — define nodes (tools), edges (flow), and problem features (keywords).

**Build a different domain**: Chaeshin is domain-agnostic. Replace cooking tools with your own (API calls, database queries, file operations) and create cases for your use case.

**Run tests**:

```bash
make test
```

---

*See [README](../README.md) for architecture details and core concepts.*
