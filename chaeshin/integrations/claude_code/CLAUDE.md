# Chaeshin — Auto-Learning Rules (Claude Code)

You have access to Chaeshin MCP tools — a persistent procedural-memory layer for
case-based reasoning. L1 is always a ToolGraph with one or more executable Tool
nodes. L2 and higher are Procedures that normally group five to seven Cases from
the immediately lower layer. Outcomes start as `pending` until a human gives a
verdict.

---

## Mental Model — read this once

- **ToolGraph base, Procedures above it.** An L1 `Case` stores a ToolGraph. An
  L2+ `Case` stores a Procedure whose normally five to seven ProcedureSteps anchor
  Cases from the immediately lower layer. Recursively following those anchors must
  terminate at L1 ToolGraphs. There is no fixed maximum layer.
- **Search every layer together.** Retrieval does not predict one layer and search
  only there. L1 ToolGraphs and all L2+ Procedures compete in one candidate space;
  relation expansion then adds relevant parent, child, and prerequisite context.
- **Tri-state outcome.** `outcome.status` is `pending` | `success` | `failure`. `chaeshin_retain` always saves as `pending`. **Never** infer success/failure yourself. Only call `chaeshin_verdict` when the user explicitly judges (their own words quoted in `note`).
- **No verdict ≠ failure.** A case that times past its `deadline_at` without a verdict stays `pending`. That's a real state, not a missing one.
- **Edits are versioned.** `chaeshin_revise` preserves the previous HEAD as a snapshot, then rewrites the live case in place. Downstream children keep the same `parent_case_id`.
- **Edits cascade.** If a revised graph removes a node, Chaeshin auto-flips downstream children anchored to that removed node back to `pending`.

---

## Tool Reference (14 tools)

| Tool | When |
|------|------|
| `chaeshin_retrieve` | **Always first.** Search past cases before you start any non-trivial task. |
| `chaeshin_retain` | Save an L1 ToolGraph or an L2+ Procedure Case. Always saved as `pending`. |
| `chaeshin_update` | Patch metadata / problem_features / outcome (not the graph itself). |
| `chaeshin_revise` | Commit a new ToolGraph/Procedure structure revision. Cascades to orphan children. |
| `chaeshin_history` | Inspect HEAD → previous snapshot revision history. |
| `chaeshin_diff` | Compare two version Case IDs by ToolGraph/Procedure structure. |
| `chaeshin_revert` | Restore an older revision's graph into HEAD as a new commit (`to_index` or `tag`). |
| `chaeshin_blame` | Per current node, which revision introduced it + that commit's reason. |
| `chaeshin_tag` | Name the current revision (or list tags). Revert by name with `chaeshin_revert(tag=...)`. |
| `chaeshin_delete` | Remove a case (with reason). |
| `chaeshin_verdict` | Record user's `success` / `failure` judgment. **User authority only.** |
| `chaeshin_feedback` | Free-form natural-language feedback (escalate/modify/correct/…). |
| `chaeshin_decompose` | Get decomposition context for complex tasks. |
| `chaeshin_stats` | Inspect live case counts, snapshots, layers, and outcome distribution. |

---

## Before Multi-Step Tasks — `chaeshin_retrieve`

Call **before** any task involving 3+ tool calls or that spans sessions:

- bug fix · feature implementation · refactoring · deploy · CI fix · planning · etc.
- Pass the user's request as `query`, extract `keywords` from context.

The response splits into three lists:
- `successes` — past cases with verdict=success. Treat them as evidence, even at
  high similarity; never execute the top-ranked structure automatically.
- `warnings` — past cases with verdict=failure. **Avoid** these patterns.
- `pending` — past cases still awaiting verdict. Treat as "unknown signal" — informational only.

If `include_children=true` you get anchored lower Procedures and L1 ToolGraphs too.
Use this for bounded procedural context, not as an executable plan.

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

For tasks that span multiple decomposition layers, call `chaeshin_retain` once
per Case, top-down, chaining `parent_case_id` / `parent_node_id`. The current MCP
payload uses the legacy `graph` container for both kinds, but its meaning is
different by layer: L2+ nodes are ProcedureSteps; only L1 nodes are executable
Tools.

```
1) chaeshin_retain(layer="L{n}", depth=n-1, graph={5–7 procedure steps}, ...) → root_id
2) For each ProcedureStep, retain the Case from the immediately lower layer:
   chaeshin_retain(
     layer="L{n-1}", depth=n-2,
     parent_case_id=root_id,
     parent_node_id=<that procedure step's id>,
     graph={... lower Procedure or L1 ToolGraph ...}
   )
3) Stop at layer="L1". An L1 ToolGraph may contain several actual Tool nodes and
   control-flow edges; L1 does not mean one Tool call.
```

Chaeshin links parent ↔ child automatically when you pass `parent_case_id` + `parent_node_id`.

### L1 ToolGraph Format

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

`params_hint` (node) and `condition` (edge) are optional but useful for branchy
flows. For L2+, the corresponding container represents ordered or guarded
ProcedureSteps and child anchors, not registered Tools.

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

## When the Stored Procedure or ToolGraph Changes — `chaeshin_revise`

When user feedback is about the **Procedure or ToolGraph structure** ("이 단계 빼", "순서 바꿔", "이걸 두 개로 쪼개"), don't just log feedback — create a structural revision:

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

Use `chaeshin_update` (not `revise`) for non-structural edits like changing
`outcome` fields or `metadata` directly. Use `revise` whenever a ToolGraph or
Procedure changes.

---

## Retrieve Cascade — Reading Trees Back

`chaeshin_retrieve(query=..., include_children=true)` walks the Procedure anchors
downward from each match, returning lower Procedures and L1 ToolGraphs. Use this
when bringing context back for a complex task.

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
