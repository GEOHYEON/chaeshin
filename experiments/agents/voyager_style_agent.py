"""Voyager-style flat skill library.

We re-implement the core Voyager (Wang et al., NeurIPS 2023) idea —
an ever-growing library of *successful* trajectories indexed by task
description embedding — but adapted to text benchmarks.

Differences from canonical Voyager (which targets Minecraft):
- Skills are stored as full action sequences (not Python code)
- No automatic curriculum (the benchmark provides task order)
- Self-verification is delegated to the benchmark's outcome signal

This stays an honest baseline for chaeshin's "persistent memory" claim:
both systems retain across tasks, but Voyager-style is *flat* (no
recursion) and *binary* (no pending state).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from experiments.agents.base import Agent, RunRecord, StepRecord
from experiments.agents._react_core import react_loop
from experiments.benchmarks.base import ToolSpec


@dataclass
class _Skill:
    """One stored successful trajectory."""
    task_description: str
    actions: List[Dict[str, Any]]  # list of {tool, args, observation}
    final: str
    embedding: Optional[List[float]] = None


class _SkillLibrary:
    """In-memory flat skill bank. Persists across calls to the same agent instance."""

    def __init__(self):
        self.skills: List[_Skill] = []

    def add(self, skill: _Skill):
        self.skills.append(skill)

    def retrieve(self, query: str, top_k: int = 1) -> List[_Skill]:
        # Bag-of-words Jaccard for harness simplicity.
        # In a real Voyager port this would be embedding-based.
        q = set(query.lower().split())
        scored = []
        for s in self.skills:
            d = set(s.task_description.lower().split())
            inter = len(q & d)
            union = len(q | d) or 1
            scored.append((s, inter / union))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:top_k] if scored]


class VoyagerStyleAgent(Agent):
    name = "voyager_style"

    def __init__(self):
        self.lib = _SkillLibrary()

    def _format_skill(self, s: _Skill) -> str:
        steps = "\n".join(
            f"  {i}. {a['tool']}({json.dumps(a['args'], ensure_ascii=False)}) → {a['observation'][:80]}"
            for i, a in enumerate(s.actions)
        )
        return f"Past success on '{s.task_description}':\n{steps}"

    async def run(self, env, adapter, max_steps: int = 30) -> RunRecord:
        # 1. Retrieve relevant past skill
        task_desc = env.observe().split("\n")[0][:200]
        retrieved = self.lib.retrieve(task_desc, top_k=1)

        pre_messages = []
        if retrieved:
            pre_messages.append({
                "role": "user",
                "content": (
                    "Skill library — most-similar past success:\n"
                    + self._format_skill(retrieved[0])
                    + "\n\nReuse this approach if it applies."
                ),
            })

        # 2. Run ReAct loop (no extra tools — flat memory means no chaeshin tools)
        steps, final, tokens, latency = await react_loop(
            env,
            adapter,
            role_hint=(
                "You are an agent with a personal skill library of past successes. "
                "If a similar past skill is provided, follow it; otherwise solve from scratch."
            ),
            pre_messages=pre_messages,
            max_steps=max_steps,
        )
        outcome = env.outcome()

        # 3. On success, retain the trajectory as a new skill
        if outcome.success and steps:
            actions = [
                {"tool": s.action, "args": s.action_input, "observation": s.observation}
                for s in steps
                if s.action and s.action != "<final>"
            ]
            if actions:
                self.lib.add(_Skill(
                    task_description=task_desc,
                    actions=actions,
                    final=final,
                ))

        return RunRecord(
            agent_name=self.name,
            benchmark_name="",
            task_id="",
            seed=0,
            steps=steps,
            final_answer=final,
            success=outcome.success,
            failure_reason="" if outcome.success else outcome.reason,
            tokens_used=tokens,
            latency_seconds=latency,
            extras={
                "retrieved_skill": retrieved[0].task_description if retrieved else None,
                "lib_size": len(self.lib.skills),
            },
        )
