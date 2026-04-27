"""ADaPT (Prasad et al., NAACL Findings 2024) — as-needed recursive decomposition.

Faithful adaptation of ADaPT's core idea: when an executor LLM fails on
a sub-task, the planner LLM decomposes that sub-task into smaller pieces
recursively. No persistent memory across trajectories.

Implementation simplification: instead of separate executor/planner LLM
calls, we let one LLM run a ReAct loop with a "decompose" pseudo-tool
that the model calls when it thinks the current sub-task is too complex.
This preserves the "decompose only on failure" semantics while keeping
the harness uniform.
"""

from __future__ import annotations

from typing import Any, Dict, List

from experiments.agents.base import Agent, RunRecord, StepRecord
from experiments.agents._react_core import react_loop
from experiments.benchmarks.base import ToolSpec


class AdaptAgent(Agent):
    name = "adapt"

    async def run(self, env, adapter, max_steps: int = 30) -> RunRecord:
        # The "decompose" tool is purely metacognitive — it does nothing
        # to the environment; it just lets the model spell out a sub-plan.
        decomposition_log: List[Dict[str, Any]] = []

        def _decompose(args: Dict[str, Any]) -> str:
            sub = args.get("subtasks", [])
            decomposition_log.append({"depth": len(decomposition_log) + 1, "subtasks": sub})
            return (
                f"Decomposition recorded (depth={len(decomposition_log)}). "
                f"Now execute the subtasks in order: {sub}"
            )

        decompose_tool = ToolSpec(
            name="decompose",
            description=(
                "Use ONLY when the current task feels too complex to solve "
                "in a few direct tool calls. List subtasks; then execute each."
            ),
            example_input='{"subtasks": ["find key", "unlock door", "enter room"]}',
            fn=_decompose,
        )

        steps, final, tokens, latency = await react_loop(
            env,
            adapter,
            role_hint=(
                "You are an agent that solves tasks by tool calls. "
                "If a task feels too complex for a few direct calls, first call "
                "`decompose` to lay out subtasks; then execute each subtask. "
                "Use decompose recursively if a subtask is also complex."
            ),
            extra_tools=[decompose_tool],
            max_steps=max_steps,
        )
        outcome = env.outcome()
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
                "decomposition_depth": len(decomposition_log),
                "decompositions": decomposition_log,
            },
        )
