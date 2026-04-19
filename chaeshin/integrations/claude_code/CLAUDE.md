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

## Graphs All the Way Down — Mental Model

Every case stores a Tool Graph. **A node in that graph isn't necessarily atomic.** If one node still needs more than a single tool call, unfold it — that unfolding is another case with its own Tool Graph, linked back through `parent_node_id`.

Keep unfolding until every leaf is one tool call:
- `depth=0` / `layer="L1"` — atomic tool call (the leaf). Don't unfold further.
- `depth=n>0` / `layer="L{n+1}"` — a node that still needs its own graph to describe it.

The layer label is just a display name. The real question is always: "can this node be accomplished in one tool call? if yes, stop. if no, unfold."

## Decomposing Complex Requests

For complex tasks (multi-step, high-stakes, spans sessions), call `chaeshin_decompose` first. It returns:
- similar past cases for reference
- the `layer_schema` (recursive model, not fixed 3 levels)
- a `retain_protocol` with example call sequences including verdict

You (the host AI) do the actual unfolding, then persist the tree yourself — always from the outermost layer downward:

```
1. chaeshin_retain(layer="L{n}", depth=n-1, request=..., graph={...})    → root case_id
2. For each still-composite node, recurse:
     chaeshin_retain(layer="L{n-1}", depth=n-2,
                     parent_case_id=<upper case_id>,
                     parent_node_id=<that node's id>,
                     graph={... the unfolding ...})
3. Stop when graph.nodes are all atomic tool calls (depth=0).
```

Chaeshin sets parent/child links automatically when you pass `parent_case_id` + `parent_node_id`.

## Editing a Layer's Graph — Use `chaeshin_revise`

When the user's feedback is about the graph structure itself ("이 단계 빼", "순서 바꿔", "이 중간 단계를 두 개로 쪼개"), don't just log feedback — rewrite the graph:

```
chaeshin_revise(
  case_id=<this layer's id>,
  graph={"nodes":[...], "edges":[...]},
  reason="<why the graph changed>",
  cascade=true   # default
)
```

Chaeshin replaces this layer's graph and then handles the cascade:
- Children whose `parent_node_id` no longer exists in the new graph are flipped back to `outcome="pending"` with a `[cascade]` entry in `feedback_log` — they're orphaned and need your review.
- `added_nodes` (nodes that didn't exist before) come back in the response. For each new node: is it atomic? retain no child. Still composite? retain a child case under it via `parent_node_id`.

Use `chaeshin_update` for non-graph edits (outcome, metadata, problem_features). Use `chaeshin_revise` when the graph itself changes — the cascading is the point.

## Authoritative Verdicts — `chaeshin_verdict`

Never infer success/failure from vibes. When the user gives an explicit judgment ("됐다", "이거 아닌데"), call `chaeshin_verdict(case_id, "success"|"failure", note=<user's own words>)`. No verdict yet? Leave it as `pending` — that's a real state, not a missing one.

## Retrieve Cascade

`include_children=true` on a retrieved case returns the full unfolding (deeper graphs) in one call. `include_parent=true` on a leaf hit walks back up so you discover which higher-layer strategy it belonged to.

## When NOT to Use

- Simple single-tool operations (reading one file, running one command)
- Pure conversation with no tool use
- Tasks the user explicitly says are one-off
