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

**Learn from experience without replacing ReAct.** Store executable detail as L1
ToolGraphs and reusable higher-level structure as L2+ Procedures that normally
group five to seven Cases from the immediately lower layer. Retrieve all layers
together when similar situations arise and expose the bounded evidence as LLM
context. This applies the Case-Based Reasoning (CBR) cycle — Retrieve → Reuse →
Revise → Retain — to LLM tool calling.

This is neither "giving fish" (hardcoded pipelines) nor "making them catch
bare-handed" (memoryless ReAct). It is **"teaching how to fish."** Chaeshin does
not hand the agent an executable plan: the Host ReAct model reads the retrieved
Procedure/ToolGraph context and current Situation, then chooses one next Tool
directly after every Observation.

## Technical Differentiators

1. **ToolGraph Base + Procedure Hierarchy**: L1 is always a ToolGraph with one or
   more executable Tool nodes. L2+ is a Procedure of normally five to seven
   immediate-lower-layer Cases. Following ProcedureStep anchors terminates at L1.

2. **All-layer, Situation-aware Retrieval**: L1 through LN enter one candidate
   space. ProblemFeatures, current state, outcomes, provenance, and typed relations
   determine the bounded context; layer is not a pre-search routing gate.

3. **Observation-driven ReAct Use**: Every Tool result may change the Situation.
   ReAct reassesses it, optionally requeries Chaeshin, and selects the next Tool.
   Chaeshin does not run an applicability classifier, Planner, or graph executor in
   front of that decision.

4. **Versioned, Governed Memory**: Structural changes create traceable revisions;
   outcomes, provenance, validity, review state, and tool-schema compatibility are
   managed separately.

## Inspirations

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943)
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453)
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291)
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1)
- [HTN Plan Repair Algorithms (2025)](https://arxiv.org/abs/2504.16209)

## What We Believe

- Agents should learn from experience
- Procedural evidence should be structured and provenance-linked
- ReAct should use memory as context, not surrender control to a stored plan
- Tool choice should change when the Situation or latest Observation changes
- Good frameworks should be domain-agnostic

Chaeshin can be a chef, a doctor, or a coding agent. Just swap the tools and cases.

---

*"Give an agent a plan, it solves one task. Teach it to retrieve plans, it solves them all."*
