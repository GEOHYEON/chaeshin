# Chaeshin Project — Claude Code Rules

## Chaeshin CBR Memory (MCP)

This project has a Chaeshin MCP server registered. Use it to build up memory of successful (and failed) patterns.

### Before multi-step tasks

Always call `chaeshin_retrieve` before starting any non-trivial task:

- Bug fix, feature implementation, refactoring, deployment, CI fix, etc.
- Pass the user's request as `query`, extract `keywords` from context
- If a matching case exists (similarity > 0.7), follow that tool graph
- If `warnings` are returned, **avoid** those patterns — they failed before

### After completing a task

**Success** — call `chaeshin_retain`:
- `request`: what the user asked
- `category`: type of work (e.g. "bug-fix", "feature", "ci", "refactor", "deploy")
- `keywords`: relevant terms for future matching
- `graph`: the tool execution steps as nodes/edges
- `satisfaction`: estimate 0-1 based on outcome

**Failure** — also call `chaeshin_retain`:
- Set `success: false`
- Set `error_reason`: why it failed (e.g. "onnxruntime has no Python 3.10 wheel")
- This prevents repeating the same mistake

### Tool graph structure

When saving a graph, map your actions to nodes:
- Each significant step = one node (read file, edit, run test, git commit, etc.)
- Edges connect sequential steps
- Conditions on edges for branching (e.g. "test passed" → commit, "test failed" → fix)

Example for a typical fix-and-push flow:
```json
{
  "nodes": [
    {"id": "n1", "tool": "read_code", "note": "Understand the issue"},
    {"id": "n2", "tool": "edit_code", "note": "Apply fix"},
    {"id": "n3", "tool": "run_tests", "note": "Verify fix"},
    {"id": "n4", "tool": "git_commit", "note": "Commit changes"},
    {"id": "n5", "tool": "git_push", "note": "Push to remote"},
    {"id": "n6", "tool": "check_ci", "note": "Verify CI passes"}
  ],
  "edges": [
    {"from": "n1", "to": "n2"},
    {"from": "n2", "to": "n3"},
    {"from": "n3", "to": "n4", "condition": "n3.output.passed == true"},
    {"from": "n3", "to": "n2", "condition": "n3.output.passed == false"},
    {"from": "n4", "to": "n5"},
    {"from": "n5", "to": "n6"}
  ]
}
```

## Project Conventions

- Language: Python 3.10+ with `from __future__ import annotations`
- Dependencies: structlog for logging, dataclasses for schemas
- Tests: pytest + pytest-asyncio, run with `uv run pytest tests/ -v`
- CI: GitHub Actions matrix (3.10, 3.11, 3.12), use `uv sync --extra dev` (NOT `--all-extras`)
- Integrations: optional extras (openai, chroma, llm, demo)
- Entry point: `chaeshin` CLI via `[project.scripts]`
- Korean comments in core code, English in README/docs
- Monitor UI: Next.js (chaeshin-monitor/), shadcn/ui + React Flow
