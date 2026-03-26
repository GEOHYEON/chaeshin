---
name: chaeshin
description: "CBR memory layer — remembers how you do things, not just what you like. Retrieves successful tool execution graphs and warns about past failures."
---

# Chaeshin — Tool Graph Memory

You have access to Chaeshin, a Case-Based Reasoning memory layer that remembers **how** tasks were executed before — both successes and failures.

## How It Works

Before executing a multi-step task, check if a similar case exists:

```bash
python -m chaeshin.integrations.openclaw.bridge retrieve "사용자 요청 텍스트"
```

The output includes successful cases (to follow) and **warnings** about similar past failures (to avoid).

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
2. If a case is found with similarity > 0.7, follow that graph (adapt if needed)
3. If **warnings** are returned, avoid the patterns that failed before
4. If no case found, proceed normally — then save the result
5. Save both successes AND failures — failures must include `--error-reason`
6. The tool graph is the source of truth, not a text summary
