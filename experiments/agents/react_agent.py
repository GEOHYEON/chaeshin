"""Vanilla ReAct (Yao et al., ICLR 2023) — the no-memory baseline."""

from __future__ import annotations

from experiments.agents.base import Agent, RunRecord
from experiments.agents._react_core import react_loop


class ReActAgent(Agent):
    name = "react"

    async def run(self, env, adapter, max_steps: int = 30) -> RunRecord:
        steps, final, tokens, latency = await react_loop(
            env,
            adapter,
            role_hint="You are an agent solving a task by calling tools step by step.",
            max_steps=max_steps,
        )
        outcome = env.outcome()
        return RunRecord(
            agent_name=self.name,
            benchmark_name="",  # filled by runner
            task_id="",         # filled by runner
            seed=0,
            steps=steps,
            final_answer=final,
            success=outcome.success,
            failure_reason="" if outcome.success else outcome.reason,
            tokens_used=tokens,
            latency_seconds=latency,
        )
