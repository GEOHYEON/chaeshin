"""Reflexion (Shinn et al., NeurIPS 2023) — verbal self-reflection across trials.

Implementation note: the canonical Reflexion paper does *up to k* trials
per task, generating a verbal reflection after each failure that gets
prepended to the next trial. Our experimental harness orchestrates this
externally — i.e. the runner calls `ReflexionAgent.run` up to k times
and feeds the previous trial's reflection back via `prior_reflections`.
"""

from __future__ import annotations

from typing import List, Optional

from experiments.agents.base import Agent, RunRecord
from experiments.agents._react_core import react_loop


class ReflexionAgent(Agent):
    name = "reflexion"

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self._reflections: List[str] = []

    async def _generate_reflection(self, adapter, run_record: RunRecord) -> str:
        """Have the LLM produce a one-paragraph verbal reflection on the failed trial."""
        trace = "\n".join(
            f"Step {s.step_idx}: action={s.action} input={s.action_input} obs={s.observation[:120]}"
            for s in run_record.steps
        )
        prompt = [
            {"role": "system", "content": (
                "You are a meta-reasoner. Given an agent's failed trial, "
                "produce ONE paragraph of concrete advice for the next "
                "attempt — what to try, what to avoid. ≤ 80 words."
            )},
            {"role": "user", "content": f"Failed trial:\n{trace}\n\nFinal: {run_record.final_answer}"},
        ]
        text = await adapter.llm_fn(prompt)
        return text.strip()

    async def run(self, env, adapter, max_steps: int = 30) -> RunRecord:
        # Inject prior reflections as a "memory" message
        pre_messages = []
        if self._reflections:
            joined = "\n".join(f"- {r}" for r in self._reflections[-3:])
            pre_messages.append({
                "role": "user",
                "content": f"Reflections from previous attempts:\n{joined}\n\nApply these lessons.",
            })

        steps, final, tokens, latency = await react_loop(
            env,
            adapter,
            role_hint=(
                "You are an agent solving a task by calling tools step by step. "
                "If reflections from previous attempts are provided, use them."
            ),
            pre_messages=pre_messages,
            max_steps=max_steps,
        )
        outcome = env.outcome()
        record = RunRecord(
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
            extras={"prior_reflections": list(self._reflections)},
        )

        # On failure: generate a reflection that future runs of *this same agent
        # instance* on the same task will see. The runner is expected to keep
        # the agent instance per-task across trials.
        if not outcome.success:
            try:
                refl = await self._generate_reflection(adapter, record)
                self._reflections.append(refl)
                record.extras["new_reflection"] = refl
            except Exception as e:
                record.extras["reflection_error"] = str(e)

        return record
