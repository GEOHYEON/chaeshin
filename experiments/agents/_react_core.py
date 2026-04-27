"""Shared ReAct loop used by all agents.

We extract the loop (parse Thought/Action/Action Input → execute → feed
Observation) so that the differences between systems live only in:

  1. How tools get exposed (domain tools vs domain + memory tools)
  2. The system prompt
  3. Pre-task hooks (retrieve memory) and post-task hooks (retain memory)

This avoids duplicating ~100 lines of parsing logic across six agents.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from experiments.agents.base import RunRecord, StepRecord
from experiments.benchmarks.base import Environment, ToolSpec


_ACTION_RE = re.compile(r"Action:\s*([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_INPUT_RE = re.compile(r"Action Input:\s*(\{.*?\})\s*(?:\n|$)", re.DOTALL)
_FINAL_RE = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)


def _parse_response(text: str) -> Tuple[str, Dict[str, Any]]:
    """Returns (kind, payload) where kind in {"final","action","malformed","bad_json"}."""
    final = _FINAL_RE.search(text)
    if final:
        return "final", {"answer": final.group(1).strip()}
    am = _ACTION_RE.search(text)
    im = _INPUT_RE.search(text)
    if not am or not im:
        return "malformed", {}
    try:
        args = json.loads(im.group(1))
    except json.JSONDecodeError as e:
        return "bad_json", {"error": str(e), "raw": im.group(1)}
    return "action", {"tool": am.group(1), "args": args}


def _format_tools(tools: List[ToolSpec]) -> str:
    return "\n".join(
        f"- {t.name}: {t.description}\n  example input: {t.example_input}"
        for t in tools
    )


def build_system_prompt(
    *,
    role_hint: str,
    tools: List[ToolSpec],
    extra_instructions: str = "",
) -> str:
    return f"""{role_hint}

Output format (strict):
Thought: <one sentence reasoning>
Action: <tool name from list below>
Action Input: <one-line JSON>

After your action, the next user message will start with "Observation:" — read it and continue with another Thought / Action / Action Input. End by emitting:

Final Answer: <one-sentence summary>

Tools:
{_format_tools(tools)}

Rules:
- Emit exactly one Thought / Action / Action Input per turn.
- Action Input MUST be valid one-line JSON.
- Stop ONLY by emitting "Final Answer: ..." — do not stop otherwise.
{extra_instructions}"""


async def react_loop(
    env: Environment,
    adapter,
    *,
    role_hint: str,
    extra_tools: Optional[List[ToolSpec]] = None,
    extra_instructions: str = "",
    pre_messages: Optional[List[Dict[str, str]]] = None,
    max_steps: int = 30,
) -> Tuple[List[StepRecord], str, int, float]:
    """Run a ReAct trial against `env`. Returns (steps, final_answer, tokens, latency).

    `extra_tools` are appended to the env tools (e.g. memory tools for chaeshin).
    `pre_messages` are inserted between system + user (e.g. retrieved cases).
    """
    tools = list(env.tools()) + list(extra_tools or [])
    tool_map = {t.name: t for t in tools}

    system_prompt = build_system_prompt(
        role_hint=role_hint,
        tools=tools,
        extra_instructions=extra_instructions,
    )
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if pre_messages:
        messages.extend(pre_messages)
    messages.append({"role": "user", "content": env.observe()})

    steps: List[StepRecord] = []
    final_answer = ""
    tokens_used = 0
    t0 = time.time()

    for step_idx in range(max_steps):
        if env.is_done():
            break
        try:
            text = await adapter.llm_fn(messages)
        except Exception as e:
            steps.append(StepRecord(step_idx=step_idx, error=f"llm_call_failed: {e!r}"))
            break

        kind, payload = _parse_response(text)

        if kind == "final":
            final_answer = payload["answer"]
            steps.append(StepRecord(step_idx=step_idx, thought=text, action="<final>"))
            break

        if kind in ("malformed", "bad_json"):
            steps.append(StepRecord(
                step_idx=step_idx,
                thought=text,
                error=f"parse_{kind}",
            ))
            messages.append({"role": "assistant", "content": text})
            messages.append({
                "role": "user",
                "content": "Output did not parse. Respond with Thought: / Action: / Action Input: in that order.",
            })
            continue

        # kind == "action"
        tool_name = payload["tool"]
        args = payload["args"]
        spec = tool_map.get(tool_name)
        if spec is None:
            obs = f"unknown tool '{tool_name}'. Available: {list(tool_map)}"
        else:
            try:
                result = spec.fn(args)
                if hasattr(result, "__await__"):
                    result = await result
                obs = str(result) if not isinstance(result, str) else result
            except Exception as e:
                obs = f"tool error: {e!r}"

        # If the tool was a domain action and env is now done, capture that.
        # The agent still gets the observation but we'll exit on next iteration.

        steps.append(StepRecord(
            step_idx=step_idx,
            thought=text,
            action=tool_name,
            action_input=args,
            observation=obs,
        ))
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": f"Observation: {obs}"})

    latency = time.time() - t0
    return steps, final_answer, tokens_used, latency
