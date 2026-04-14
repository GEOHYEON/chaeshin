# Chaeshin (채신) 採薪

**LLM agents that remember what worked.** Instead of improvising tool calls every time, Chaeshin stores successful execution patterns and reuses them — so your agent gets better with every task.

<p align="center">
  <img src="assets/comparison.svg" alt="Plain LLM vs Chaeshin — the same mistake vs learned pattern" width="820"/>
</p>

[한국어](docs/ko/README.md) | [中文](docs/zh/README.md) | [日本語](docs/ja/README.md) | [Español](docs/es/README.md) | [Français](docs/fr/README.md) | [Deutsch](docs/de/README.md)

---

## The Problem

Most LLM agents either **improvise** tool calls on the fly or follow **hardcoded** pipelines:

- **Improvised** (ReAct-style): Skips steps, wrong order, repeats the same mistakes.
- **Hardcoded**: Every new scenario needs code changes. Doesn't scale.

## The Fix

Chaeshin remembers what worked. When a similar request comes in, it retrieves a proven tool execution graph, adapts it, runs it, and saves the result. This is [Case-Based Reasoning](https://en.wikipedia.org/wiki/Case-based_reasoning): **Retrieve → Reuse → Revise → Retain.**

Failures are saved too — so the same mistake never happens twice.

```
Day 1:   Agent improvises everything from scratch
Day 7:   20 cases saved — common patterns are reused
Day 30:  100+ cases — agent rarely improvises, follows proven patterns
```

---

## Quick Start

### 1. Install

```bash
pip install chaeshin
```

### 2. Connect to your agent

```bash
chaeshin setup claude-code       # Claude Code (MCP + auto-learning)
chaeshin setup claude-desktop    # Claude Desktop
chaeshin setup openclaw          # OpenClaw
```

That's it. Claude now automatically:
- **Before** multi-step tasks → retrieves past patterns
- **After** completing tasks → saves the execution graph
- **On failure** → saves the failed pattern so it's never repeated

<details>
<summary>Other install methods</summary>

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv pip install chaeshin
```

With `uvx` (no global install):

```bash
uvx chaeshin setup claude-code --uvx
```

Manual MCP setup (add to `~/.claude.json`):

```json
{
  "mcpServers": {
    "chaeshin": {
      "command": "uv",
      "args": ["tool", "run", "chaeshin-mcp"]
    }
  }
}
```
</details>

<details>
<summary>Use as a standalone library (any agent)</summary>

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="send daily PR summary to slack"))
if results:
    graph = results[0][0].solution.tool_graph
```
</details>

### 3. Try the demo

```bash
git clone https://github.com/GEOHYEON/chaeshin.git && cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent   # no API key needed
```

<details>
<summary>LLM + VectorDB demo (OpenAI + ChromaDB)</summary>

```bash
cp .env.example .env         # add your OPENAI_API_KEY
uv run python -m examples.cooking.chef_agent_llm
```
</details>

<details>
<summary>Web UI demo (Gradio)</summary>

```bash
cp .env.example .env
uv run python -m examples.cooking.app
```
</details>

See the [Quick Start Guide](docs/quickstart.md) for a full walkthrough.

---

## How It Works

### Tool Graph

Tool calls are structured as a **graph** — not a simple list. Nodes are tool invocations; edges define order and conditions. Loops are supported (e.g., "taste → too bland → cook more → taste again").

<p align="center">
  <img src="assets/tool-graph.svg" alt="Tool Graph — nodes, edges, conditions, loops" width="720"/>
</p>

### Immutable Graph + Mutable Context

The graph never changes during execution. Only the **execution context** (cursor, node states, outputs) updates. If something unexpected happens and no edge matches, the LLM modifies the graph via a minimal **diff** — not a full regeneration.

### When Things Go Wrong

Real execution doesn't always follow the plan. Chaeshin handles this through **diff-based replanning**:

<p align="center">
  <img src="assets/replan-scenarios.svg" alt="Replan — phone call, allergy alert, missing ingredient" width="780"/>
</p>

---

## Full Example — Setting a Dinner Table

A complete walkthrough: "Prepare dinner for 3, kid has shrimp allergy." Shows every step — retrieve, decompose into layers, parallel cooking, taste-check loops, and failure escalation.

<p align="center">
  <img src="assets/dinner-table-success.svg" alt="Success — Retrieve → Decompose → Execute → Retain" width="820"/>
</p>

<p align="center">
  <img src="assets/dinner-table-failure.svg" alt="Failure — Escalation from L1 → L2 → User → Recovery" width="820"/>
</p>

Full scenario with step-by-step explanations:
[English](examples/dinner-table/scenario_en.md) ·
[한국어](examples/dinner-table/scenario_ko.md) ·
[日本語](examples/dinner-table/scenario_ja.md) ·
[中文](examples/dinner-table/scenario_zh.md)

---

## Integrations

All platforms share `~/.chaeshin/cases.json` — cases saved in Claude Code work in OpenClaw and vice versa.

<p align="center">
  <img src="assets/integrations.svg" alt="Integration Architecture — Claude Code & OpenClaw" width="820"/>
</p>

| Platform | Command | What it does |
|----------|---------|-------------|
| Claude Code | `chaeshin setup claude-code` | MCP server + auto-learning rules (`CLAUDE.md`) |
| Claude Desktop | `chaeshin setup claude-desktop` | Auto-edits `claude_desktop_config.json` |
| OpenClaw | `chaeshin setup openclaw` | Installs `SKILL.md` into workspace |

Three tools become available after setup:

| Tool | Description |
|------|-------------|
| `chaeshin_retrieve` | Search past cases — returns successes and failures separately |
| `chaeshin_retain` | Save execution graphs (successes and failures) |
| `chaeshin_stats` | View case store statistics |

---

## Monitor — Visual Graph Editor

<p align="center">
  <img src="assets/tool-graph.svg" alt="Visual Graph Editor" width="720"/>
</p>

A web-based tool graph editor built with Next.js and React Flow. Drag-and-drop nodes, draw edges, set conditions, import/export cases from `~/.chaeshin/cases.json`.

```bash
cd chaeshin-monitor && pnpm install && pnpm dev
```

---

## Architecture

<p align="center">
  <img src="assets/architecture.svg" alt="Chaeshin Architecture" width="600"/>
</p>

<details>
<summary>Project structure</summary>

```
chaeshin/
├── schema.py               # Core data types (Case, ToolGraph, GraphNode, GraphEdge)
├── case_store.py           # CBR 4R cycle: retrieve, reuse, revise, retain
├── graph_executor.py       # Tool graph runner (parallel, loops, conditions)
├── planner.py              # LLM-based graph create / adapt / replan (diff-based)
├── cli/                    # chaeshin setup claude-code / claude-desktop / openclaw
├── integrations/
│   ├── claude_code/        # MCP server (FastMCP) + CLAUDE.md auto-learning template
│   ├── openclaw/           # SKILL.md + bridge CLI
│   ├── openai.py           # LLM + embedding adapter
│   ├── chroma.py           # ChromaDB vector case store
│   └── chaebi.py           # Chaebi marketplace sync
└── agents/                 # v2: Orchestrator, Decomposer, Executor, Reflection
chaeshin-monitor/           # Next.js web UI
examples/cooking/           # Demo agent (kimchi stew, doenjang stew, recovery scenarios)
examples/dinner-table/      # Full walkthrough (4 languages)
```
</details>

## Requirements

- Python 3.10+
- No required dependencies for core usage
- Optional: `openai` (LLM adapter), `chromadb` (vector store), `httpx` (Chaebi marketplace)

## Related Work

Chaeshin builds on ideas from:

- [CBR for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM integration survey
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — CBR-based data science agent
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — Skill library with experience-driven learning
- [GAP (2025)](https://arxiv.org/html/2510.25320v1) — Parallel tool execution via graphs
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — Hierarchical plan repair

**What's different?** Tool graphs stored as CBR cases, general graphs with loops (not just DAGs), diff-based modification instead of full regeneration, and hybrid execution where code handles normal flow while the LLM only intervenes on exceptions.

## License

MIT — see [LICENSE](LICENSE)

---

*敎子採薪 — Don't give firewood; teach how to gather it.*
