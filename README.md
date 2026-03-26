# Chaeshin (채신) 採薪

> *"Give an agent a plan, it solves one task. Teach it to retrieve plans, it solves them all."*

**Chaeshin** is a Case-Based Reasoning (CBR) framework for LLM tool calling. It stores successful tool execution graphs, retrieves them for similar problems, and adapts them to new situations.

The name comes from 교자채신(敎子採薪) — *"Don't give firewood; teach how to gather it."*

[한국어](docs/ko/README.md)

---

## Why Chaeshin?

Most LLM agents either improvise tool calls on the fly (ReAct-style) or follow rigid pipelines hardcoded by developers. Both approaches have limitations:

- **Improvised**: The LLM might skip steps, call tools in the wrong order, or repeat mistakes it made before.
- **Hardcoded**: Every new scenario requires code changes. Doesn't scale.

Chaeshin takes a different approach: **remember what worked, and reuse it.**

When a request comes in, Chaeshin searches for a similar past case, pulls out the tool execution graph that worked, adapts it if needed, runs it, and — if successful — saves it back for future use. This is the classic [Case-Based Reasoning](https://en.wikipedia.org/wiki/Case-based_reasoning) cycle: **Retrieve → Reuse → Revise → Retain**.

## Plain LLM vs Chaeshin

<p align="center">
  <img src="assets/comparison.svg" alt="Plain LLM vs Chaeshin — cheese toast comparison" width="820"/>
</p>

## Core Concepts

### Tool Graph

Tool calls are structured as a **graph** (not just a DAG — loops are supported).

<p align="center">
  <img src="assets/tool-graph.svg" alt="Tool Graph example — Kimchi Stew" width="720"/>
</p>

### CBR Case

Each case is a tuple of `(problem, solution, outcome, metadata)`:

```python
Case(
    problem_features=ProblemFeatures(
        request="Make kimchi stew",
        category="stew",
        keywords=["kimchi", "stew", "pork"],
    ),
    solution=Solution(
        tool_graph=ToolGraph(nodes=[...], edges=[...])
    ),
    outcome=Outcome(success=True, user_satisfaction=0.90),
    metadata=CaseMetadata(used_count=25, avg_satisfaction=0.88),
)
```

### Immutable Graph + Mutable Context

The tool graph itself never changes during execution. Only the **execution context** (cursor position, node states, outputs) is updated. If something unexpected happens and no matching edge exists, the LLM is asked to modify the graph via a diff — adding or removing nodes and edges.

### What Happens When Things Go Wrong?

Real-world execution doesn't always follow the plan. Chaeshin handles this through **diff-based replanning** — the LLM only intervenes when no matching edge exists:

<p align="center">
  <img src="assets/replan-scenarios.svg" alt="Replan Scenarios — Phone call, Allergy, Missing ingredient" width="780"/>
</p>

The key insight: the graph stays immutable during normal execution. Only when an exception has **no matching edge** does the LLM step in to modify the graph via a minimal diff — not a full regeneration.

## Install

```bash
pip install chaeshin
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv pip install chaeshin
```

From source:

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # recommended
# or: pip install -e ".[dev]"
```

## Quick Start

**Rule-based demo** (no API key needed):

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent
```

**LLM + VectorDB demo** (OpenAI + ChromaDB):

```bash
cp .env.example .env         # add your OPENAI_API_KEY
uv run python -m examples.cooking.chef_agent_llm
```

This runs the full CBR cycle with real LLM-powered graph creation, vector-based case retrieval, and diff-based replanning.

**Web UI demo** (Gradio):

```bash
cp .env.example .env         # add your OPENAI_API_KEY
uv run python -m examples.cooking.app
```

Opens a browser UI where you can enter any cooking request and watch the CBR pipeline execute step by step.

See the [Quick Start Guide](docs/quickstart.md) for a step-by-step walkthrough.

## Architecture

<p align="center">
  <img src="assets/architecture.svg" alt="Chaeshin Architecture" width="600"/>
</p>

## Related Work

Chaeshin draws on ideas from:

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM integration survey
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — CBR-based data science agent
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — Skill library with experience-driven learning
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1) — Parallel tool execution via graphs
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — Hierarchical plan repair

**What's different?** Chaeshin combines tool graph storage as CBR cases, general graphs with loops (not just DAGs), diff-based graph modification instead of full regeneration, and hybrid execution where code handles normal flow while the LLM only intervenes on exceptions.

## License

MIT License — see [LICENSE](LICENSE)

---

*敎子採薪 — Don't give firewood; teach how to gather it.*
