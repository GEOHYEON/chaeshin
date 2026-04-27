"""τ-bench adapter (retail domain).

τ-bench simulates multi-turn tool-agent-user interactions with a
database state-comparison evaluator and pass^k metric.

Installation (one-time):
    git clone https://github.com/sierra-research/tau-bench
    cd tau-bench && uv pip install -e .
    export TAUBENCH_PATH=$PWD

Reference: Yao et al. NeurIPS 2024 (arXiv:2406.12045).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator, List, Optional

from experiments.benchmarks.base import Benchmark, Environment, Outcome, Task, ToolSpec


class _TauEnv(Environment):
    """Wraps a single τ-bench retail conversation."""

    def __init__(self, tau_env, task_idx: int, max_turns: int = 30):
        self._env = tau_env
        self._task_idx = task_idx
        self._max_turns = max_turns
        self._turn = 0
        self._done = False
        self._success = False
        self._last_obs: str = ""
        self._reset()

    def _reset(self):
        obs = self._env.reset(task_index=self._task_idx)
        self._last_obs = self._render(obs)

    def _render(self, obs) -> str:
        # τ-bench obs is structured; serialize to text
        if hasattr(obs, "observation"):
            return str(obs.observation)
        return str(obs)

    def _step_once(self, action_str: str) -> str:
        # τ-bench expects {role, content} action object
        from tau_bench.types import Action
        action = Action(name="respond", kwargs={"content": action_str})
        result = self._env.step(action)
        self._turn += 1
        self._last_obs = self._render(result.observation if hasattr(result, "observation") else result)
        if hasattr(result, "done") and result.done:
            self._done = True
            self._success = bool(getattr(result, "reward", 0) >= 1.0)
        if self._turn >= self._max_turns:
            self._done = True
        return self._last_obs

    def tools(self) -> List[ToolSpec]:
        # τ-bench provides domain tools (e.g., get_user_details, modify_order).
        # Bridge each tool through the action interface.
        domain_tools = self._env.tools_info if hasattr(self._env, "tools_info") else []
        specs = [
            ToolSpec(
                name="respond_to_user",
                description="Send a natural-language reply to the simulated user.",
                example_input='{"message": "Could you confirm the order id?"}',
                fn=lambda args: self._step_once(args.get("message", "")),
            )
        ]
        for tool in domain_tools:
            tname = tool.get("name", "tool")
            tdesc = tool.get("description", "")
            specs.append(
                ToolSpec(
                    name=tname,
                    description=tdesc,
                    example_input="{}",
                    fn=lambda args, _t=tname: self._step_once(f"call:{_t}({args})"),
                )
            )
        return specs

    def observe(self) -> str:
        return self._last_obs

    def is_done(self) -> bool:
        return self._done

    def outcome(self) -> Outcome:
        return Outcome(
            success=self._success,
            steps=self._turn,
            reason="reward>=1" if self._success else "reward<1",
            benchmark_specific={"task_index": self._task_idx},
        )


class TauBenchBenchmark(Benchmark):
    """τ-bench retail tasks."""

    name = "taubench"

    def __init__(self, domain: str = "retail", max_turns: int = 30, limit: Optional[int] = None):
        self.domain = domain
        self.max_turns = max_turns
        self.limit = limit

    def _load_env(self):
        try:
            from tau_bench.envs import get_env
        except ImportError as e:
            raise ImportError(
                "τ-bench not installed. Run:\n"
                "  git clone https://github.com/sierra-research/tau-bench\n"
                "  cd tau-bench && uv pip install -e .\n"
                f"Original error: {e}"
            ) from e
        return get_env(env=self.domain, user_strategy="llm", user_model="gpt-4o-mini",
                       user_provider="openai", task_split="test", task_index=0)

    def tasks(self) -> Iterator[Task]:
        try:
            from tau_bench.envs.retail import data as retail_data  # type: ignore
        except ImportError:
            return
        n = self.limit or len(retail_data.TASKS_TEST)
        for i in range(n):
            t = retail_data.TASKS_TEST[i]
            yield Task(
                task_id=f"taubench_{i:04d}",
                description=t.instruction if hasattr(t, "instruction") else str(t),
                metadata={"task_index": i},
            )

    def make_env(self, task: Task) -> Environment:
        env = self._load_env()
        return _TauEnv(env, task_idx=task.metadata["task_index"], max_turns=self.max_turns)
