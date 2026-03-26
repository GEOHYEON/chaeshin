# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-03-25

### Added

- Core schema: `Case`, `ToolGraph`, `GraphNode`, `GraphEdge`, `ExecutionContext`
- CBR case structure following `(problem_features, solution, outcome, metadata)` tuple
- `GraphExecutor` — hybrid execution engine (code-based + LLM replan)
  - Parallel node execution support
  - Edge condition evaluation with `node.output.field == value` syntax
  - Loop detection and `max_loops` guard
  - Dynamic patient TODO generation from graph state
- `CaseStore` — CBR case storage with keyword-based retrieval
  - `retrieve()` with Jaccard similarity
  - `retain_if_successful()` with satisfaction threshold
  - JSON serialization/deserialization
- `GraphPlanner` — LLM-based graph creation, adaptation, and replanning
  - `create_graph()` from scratch
  - `adapt_graph()` to modify retrieved case for current situation
  - `replan_graph()` with diff-based graph modification
- Cooking example: kimchi stew chef agent
  - 9 cooking tools (알레르기체크, 재료확인, 썰기, 볶기, 끓이기, 간보기, 양념하기, 굽기, 담기)
  - 2 pre-built CBR cases (김치찌개, 된장찌개)
  - Full CBR cycle demo: Retrieve → Execute → Retain
