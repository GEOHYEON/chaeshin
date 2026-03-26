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

## 2. Run the Cooking Agent Demo

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

## 3. Understand the Flow

The demo follows 6 steps:

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
| `examples/cooking/chef_agent_llm.py` | LLM + VectorDB demo script |
| `examples/cooking/app.py` | Gradio web UI demo |
| `chaeshin/case_store.py` | CBR case storage and retrieval |
| `chaeshin/graph_executor.py` | Tool Graph execution engine |
| `chaeshin/planner.py` | LLM-based graph creation/adaptation/replanning |
| `chaeshin/integrations/openai.py` | OpenAI LLM + embedding adapter |
| `chaeshin/integrations/chroma.py` | ChromaDB vector case store |
| `chaeshin/schema.py` | Data models (Case, ToolGraph, Edge, Node) |

## 5. Run with LLM + VectorDB

The full-featured demo uses OpenAI for LLM calls and ChromaDB for vector-based case retrieval:

```bash
cp .env.example .env         # add your OPENAI_API_KEY
uv run python -m examples.cooking.chef_agent_llm
```

This demo:

- Embeds cases into ChromaDB using OpenAI embeddings
- Retrieves similar cases by vector similarity (not just keywords)
- Uses LLM to adapt retrieved graphs to the current situation
- Handles unexpected situations with LLM-powered diff-based replanning
- Saves successful results back to ChromaDB for future reuse

Options:

```bash
# New dish scenario — LLM creates a graph from scratch
uv run python -m examples.cooking.chef_agent_llm --scenario new

# Run both scenarios
uv run python -m examples.cooking.chef_agent_llm --scenario both

# Reset ChromaDB data
python -m examples.cooking.chef_agent_llm --reset
```

## 6. Web UI Demo (Gradio)

For an interactive web-based experience:

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
