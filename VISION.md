# Vision

[한국어](docs/ko/VISION.md)

## 敎子採薪 (Gyoja Chaesin)

> Don't give firewood; teach how to gather it.

This is the core philosophy of Chaeshin.

## The Problem

Current LLM agent tool-use approaches sit at two extremes.

**Free-form (ReAct)**: The LLM decides which tool to use on the fly, every time. Like cooking without a recipe — flexible, but it can skip critical steps or execute in the wrong order.

**Hardcoded (LangGraph, etc.)**: Developers wire execution order into code. Like hardcoding a recipe. Reliable, but requires code changes for every new scenario.

## Chaeshin's Approach

Chaeshin proposes a third way:

**Learn from experience.** Store successful tool calling patterns as graph structures, retrieve them when similar situations arise, and reuse them. This applies the Case-Based Reasoning (CBR) cycle — Retrieve → Reuse → Revise → Retain — to LLM tool calling.

This is neither "giving fish" (hardcoded pipelines) nor "making them catch bare-handed" (free-form ReAct). It's **"teaching how to fish."** The agent learns to find execution plans from past experience and adapt them to the current situation.

## Technical Differentiators

1. **Tool Graph as Case**: Execution plans are stored as node+edge graphs — a structure machines can directly execute, not code or plain text.

2. **General Graphs (not DAGs)**: Loops (backward edges) are supported. Patterns like "taste → too bland → boil again" are natural.

3. **Diff-based Replanning**: When something unexpected happens, instead of regenerating the entire graph, only a minimal diff is applied. The existing plan is preserved as much as possible.

4. **Hybrid Execution**: Normal flow is handled automatically by code; the LLM is only consulted for exceptions. A balance of speed and flexibility.

## Inspirations

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943)
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453)
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291)
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1)
- [HTN Plan Repair Algorithms (2025)](https://arxiv.org/abs/2504.16209)

## What We Believe

- Agents should learn from experience
- Execution plans should be structured (graphs, not natural language)
- Plans should adapt during execution
- Good frameworks should be domain-agnostic

Chaeshin can be a chef, a doctor, or a coding agent. Just swap the tools and cases.

---

*"Give an agent a plan, it solves one task. Teach it to retrieve plans, it solves them all."*
