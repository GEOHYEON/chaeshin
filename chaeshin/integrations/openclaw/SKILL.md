---
name: chaeshin
description: "CBR procedural-memory context — retrieves Procedure and ToolGraph evidence for ReAct next-tool selection."
---

# Chaeshin — Procedural Memory Context

You have access to Chaeshin, a Case-Based Reasoning memory layer that remembers **how** tasks were executed before — both successes and failures.

`SKILL.md` is the OpenClaw integration filename; **Skill is not a Chaeshin memory
type**. In Chaeshin, L1 is a ToolGraph and L2+ is a Procedure that normally groups
five to seven Cases from the immediately lower layer. Search results are context
for ReAct, not an executable plan. The current OpenClaw CLI bridge is a legacy
L1-only adapter until it exposes the full Procedure schema.

## How It Works

Before executing a multi-step task, check if a similar case exists:

```bash
python -m chaeshin.integrations.openclaw.bridge retrieve "사용자 요청 텍스트"
```

The output includes successful, failed, and pending evidence. Read it together with
the current Situation; do not automatically follow the highest-similarity graph.

After completing a task, save the execution pattern:

```bash
# Success
python -m chaeshin.integrations.openclaw.bridge retain --request "원본 요청" --graph '{"nodes":[...],"edges":[...]}'

# Failure — save as anti-pattern for future avoidance
python -m chaeshin.integrations.openclaw.bridge retain --no-success --error-reason "API rate limit at step 3" --request "원본 요청" --graph '{"nodes":[...],"edges":[...]}'
```

## When To Use

- **Before** starting a multi-step task: retrieve similar past cases
- **After** successfully completing a task: retain the execution graph
- **After** a task fails: save as failure with error reason so you avoid the same mistake next time
- When the user asks something you've done before: check memory first

## Behavior Rules

1. Always check Chaeshin before improvising a multi-tool sequence
2. Treat every similarity score and returned structure as reference evidence only
3. If **warnings** are returned, avoid the patterns that failed before
4. After each Tool result, refresh the Situation and choose the next Tool directly
5. If no case is found, proceed normally — then save only the actual trace
6. Save both successes AND failures — failures must include `--error-reason`
7. Retrieved memory is evidence, not the source of truth for the current run
