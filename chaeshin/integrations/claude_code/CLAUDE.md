# Chaeshin — Auto-Learning Rules (Claude Code)

You have access to Chaeshin MCP tools — a persistent memory layer for case-based reasoning. The model: every layer is a graph, you keep unfolding nodes until each leaf is a single tool call, and outcomes start as `pending` until a human gives a verdict.

---

## Mental Model — read this once

- **Graphs all the way down.** Every `Case` stores a Tool Graph. A node in that graph isn't necessarily atomic — if it's still composite, save it as another `Case` with `parent_case_id` + `parent_node_id` linking back. Keep unfolding until every leaf is one tool call. No fixed L1/L2/L3 ceiling.
- **Tri-state outcome.** `outcome.status` is `pending` | `success` | `failure`. `chaeshin_retain` always saves as `pending`. **Never** infer success/failure yourself. Only call `chaeshin_verdict` when the user explicitly judges (their own words quoted in `note`).
- **No verdict ≠ failure.** A case that times past its `deadline_at` without a verdict stays `pending`. That's a real state, not a missing one.
- **Edits cascade.** `chaeshin_revise` rewrites this layer's graph and Chaeshin auto-flips downstream children whose anchor node disappeared back to `pending`.

---

## Tool Reference (8 tools)

| Tool | When |
|------|------|
| `chaeshin_retrieve` | **Always first.** Search past cases before you start any non-trivial task. |
| `chaeshin_retain` | After completing a step, save the graph. Always saved as `pending`. |
| `chaeshin_update` | Patch metadata / problem_features / outcome (not the graph itself). |
| `chaeshin_revise` | Replace this layer's Tool Graph. Cascades to orphan children. |
| `chaeshin_delete` | Remove a case (with reason). |
| `chaeshin_verdict` | Record user's `success` / `failure` judgment. **User authority only.** |
| `chaeshin_feedback` | Free-form natural-language feedback (escalate/modify/correct/…). |
| `chaeshin_decompose` | Get decomposition context for complex tasks. |

---

## Before Multi-Step Tasks — `chaeshin_retrieve`

Call **before** any task involving 3+ tool calls or that spans sessions:

- bug fix · feature implementation · refactoring · deploy · CI fix · planning · etc.
- Pass the user's request as `query`, extract `keywords` from context.

The response splits into three lists:
- `successes` — past cases with verdict=success. Follow if similarity > 0.7.
- `warnings` — past cases with verdict=failure. **Avoid** these patterns.
- `pending` — past cases still awaiting verdict. Treat as "unknown signal" — informational only.

If `include_children=true` you get the unfolded sub-graphs too. Use this on retrieved roots for full plan context.

---

## After Completing a Task — `chaeshin_retain` (pending)

Always save what you actually executed. Pattern:

```
chaeshin_retain(
  request: "<what the user asked>",
  category: "<bug-fix|feature|deploy|...>",
  keywords: "<comma-separated>",
  graph: { nodes: [...], edges: [...] },
  layer: "L1"    # leaf if your nodes are all atomic tool calls
)
```

The case enters as `outcome.status="pending"`. You do **not** decide success/failure — that's the user's job (see `chaeshin_verdict` below).

### Decomposing Complex Tasks — Multiple Retains

For tasks that span multiple decomposition layers, call `chaeshin_retain` once per layer, top-down, chaining `parent_case_id` / `parent_node_id`:

```
1) chaeshin_retain(layer="L{n}", depth=n-1, graph={...}, ...)         → root_id
2) For each composite node in the root graph, recurse:
   chaeshin_retain(
     layer="L{n-1}", depth=n-2,
     parent_case_id=root_id,
     parent_node_id=<that node's id>,
     graph={... unfolded ...}
   )
3) Stop when graph.nodes are all atomic tool calls (depth=0, layer="L1").
```

Chaeshin links parent ↔ child automatically when you pass `parent_case_id` + `parent_node_id`.

### Graph Format

```json
{
  "nodes": [
    {"id": "n1", "tool": "Read", "note": "Read config"},
    {"id": "n2", "tool": "Edit", "note": "Apply fix"},
    {"id": "n3", "tool": "Bash", "note": "Run tests"}
  ],
  "edges": [
    {"from": "n1", "to": "n2"},
    {"from": "n2", "to": "n3", "condition": "n2.output.applied == true"}
  ]
}
```

`params_hint` (node) and `condition` (edge) are optional but useful for branchy flows.

---

## Reading User Verdict Signals — `chaeshin_verdict`

You only call `chaeshin_verdict` when the user **explicitly** signals a judgment. Don't infer.

### Success signals — call `chaeshin_verdict(status="success", note="<quote user>")`
- Positive: "됐다", "고마워", "완벽해", "좋아", "ㅇㅇ"
- Task acceptance: "커밋해줘", "푸쉬해줘", "다음 거 해줘"
- User moves to next topic without complaint after CI green / tests pass

### Failure signals — call `chaeshin_verdict(status="failure", note="<quote user> + reason")`
- Correction: "아니 그게 아니라", "이거 아닌데", "다시 해줘"
- Frustration: "이거 왜 안돼?", "이상한데"
- Rollback: "되돌려줘", "롤백해줘"

### Ambiguous → leave as pending
- User goes silent
- Mixed feedback ("그래 그건 됐고 다음은…")
- Partial completion you're unsure about

`note` should quote the user's own words. Avoid paraphrasing.

---

## When the Plan Itself Changes — `chaeshin_revise`

When user feedback is about the **graph structure** ("이 단계 빼", "순서 바꿔", "이걸 두 개로 쪼개"), don't just log feedback — rewrite the graph:

```
chaeshin_revise(
  case_id: <this layer's case_id>,
  graph: { nodes: [...new...], edges: [...new...] },
  reason: "<why>",
  cascade: true   # default
)
```

The response includes:
- `added_nodes` — new ids that weren't in the old graph. For each: is it atomic (leaf) or still composite? If composite, retain a child case under it.
- `removed_nodes` — nodes that disappeared.
- `orphaned_children` — child cases whose `parent_node_id` was in `removed_nodes`. They're auto-flipped back to `pending`. Surface this list to the user — they decide whether to revise / re-link / delete each.

Use `chaeshin_update` (not `revise`) for non-graph edits like changing `outcome` fields or `metadata` directly. Use `revise` whenever the graph changes.

---

## Retrieve Cascade — Reading Trees Back

`chaeshin_retrieve(query=..., include_children=true)` walks the tree downward from each match, returning the unfolded graphs. Use this when bringing context back for a complex task.

`include_parent=true` walks upward — useful when you hit a leaf and want to know which strategy it belonged to.

---

## When NOT to Use Chaeshin

- Single-tool operations (read one file, run one command).
- Pure conversation with no tool execution.
- Tasks the user explicitly says are one-off.

---

## Common Anti-Patterns to Avoid

- ❌ Calling `chaeshin_retain` with a `success` parameter — it doesn't exist anymore. Status is always `pending` at retain time.
- ❌ Calling `chaeshin_verdict` on your own without explicit user signal.
- ❌ Editing a graph via `chaeshin_update` instead of `chaeshin_revise` — you'll skip the cascade and leave orphaned children pointing to dead nodes.
- ❌ Saving everything as a flat L1 case when the task naturally has sub-structure. Decompose and chain via `parent_case_id`.
- ❌ Treating `pending` as failure during retrieve. It's its own state.
