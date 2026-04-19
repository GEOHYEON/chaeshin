# Chaeshin — Auto-Learning Rules

You have access to Chaeshin MCP tools for Case-Based Reasoning memory.
These tools let you remember how tasks were done before — both successes and failures.

## Before Starting Multi-Step Tasks

When the user asks you to do something that involves 3+ tool calls or a multi-step workflow:

1. Call `chaeshin_retrieve` with the user's request as `query`
2. If `successes` are returned (similarity > 0.7), follow that tool graph as a reference
3. If `failures` are returned, avoid those patterns — they failed before
4. If no similar cases found, proceed normally

## After Completing Tasks

When you finish a multi-step task:

1. Call `chaeshin_retain` with:
   - `request`: the original user request
   - `graph`: JSON of the tool execution steps you took (nodes = tools, edges = order)
   - `category`: task type (e.g. "bug-fix", "feature", "deploy", "refactor")
   - `keywords`: comma-separated terms for future matching
   - `success`: true/false
   - `error_reason`: why it failed (only when success=false)

2. Save both successes AND failures — failures prevent repeating the same mistake

## Graph Format

```json
{
  "nodes": [
    {"id": "n1", "tool": "Read", "note": "Read config file"},
    {"id": "n2", "tool": "Edit", "note": "Fix the bug"},
    {"id": "n3", "tool": "Bash", "note": "Run tests"}
  ],
  "edges": [
    {"from": "n1", "to": "n2"},
    {"from": "n2", "to": "n3"}
  ]
}
```

### Optional fields

- **`params_hint`** (node): 도구 파라미터 힌트. 어떤 파일을 수정했는지 등 구체적 맥락을 남길 때 사용.
  ```json
  {"id": "n1", "tool": "Read", "note": "설정 확인", "params_hint": {"file_path": "mcp_server.py"}}
  ```
- **`condition`** (edge): 분기 조건. 테스트 결과에 따라 다른 경로를 탈 때 사용.
  ```json
  {"from": "n3", "to": "n2", "condition": "test failed"}
  ```

필수는 아니지만, 복잡한 워크플로우를 저장할 때 유용하다.

## Hierarchy — L1 / L2 / L3

Every case now has a `layer`:
- **L1** — atomic tool-call pattern (single decisive action)
- **L2** — multi-tool workflow (composes L1 patterns)
- **L3** — strategy spanning multiple workflows

When you `chaeshin_retain`, pass `layer` (defaults to `L1`). When a case belongs under a bigger plan, pass `parent_case_id` — chaeshin links them automatically.

## Decomposing Complex Requests

For genuinely complex tasks (multi-workflow, spans sessions, high-stakes), call `chaeshin_decompose` first. It returns:
- similar cases for reference
- the layer schema
- a `retain_protocol` that tells you the call order

You (the host AI) do the actual decomposition, then persist the tree yourself:

```
1. chaeshin_retain(layer="L3", request=..., graph={...})        → L3 case_id
2. chaeshin_retain(layer="L2", parent_case_id=<L3 case_id>, graph={...})  → L2 case_id (per L3 node)
3. chaeshin_retain(layer="L1", parent_case_id=<L2 case_id>, graph={...})  → L1 case_id (per L2 node)
```

Chaeshin sets parent/child links automatically when you pass `parent_case_id`.

## Retrieve Cascade

When pulling context for a complex task, use `include_children=true` on L3 retrievals to get the full L3→L2→L1 tree in one call. Use `include_parent=true` on an L1 hit to discover which strategy it belonged to.

## When NOT to Use

- Simple single-tool operations (reading one file, running one command)
- Pure conversation with no tool use
- Tasks the user explicitly says are one-off
