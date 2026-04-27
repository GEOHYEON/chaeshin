"""WebShop adapter.

WebShop simulates a 1.18M-product e-commerce site with 12k+ instructions.
We use the textual web-page simulator (no pixel input).

Installation (one-time):
    uv pip install webshop-minimal  # community-maintained pip-installable subset
    # OR clone https://github.com/princeton-nlp/WebShop and follow setup.sh
    # then export WEBSHOP_PATH=/path/to/clone

Reference: Yao et al. NeurIPS 2022 (arXiv:2207.01206).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator, List, Optional

from experiments.benchmarks.base import Benchmark, Environment, Outcome, Task, ToolSpec


class _WebshopEnv(Environment):
    """Wraps a single WebShop session."""

    def __init__(self, web_env, instruction: str, max_steps: int = 25):
        self._env = web_env
        self._instruction = instruction
        self._max_steps = max_steps
        self._step = 0
        self._done = False
        self._reward = 0.0
        self._last_obs: str = ""
        self._reset()

    def _reset(self):
        obs, info = self._env.reset()
        self._last_obs = obs
        self._info = info or {}

    def _step_once(self, action: str) -> str:
        obs, reward, done, info = self._env.step(action)
        self._step += 1
        self._reward = reward
        self._last_obs = obs
        self._info = info or {}
        if done or self._step >= self._max_steps:
            self._done = True
        return obs

    def tools(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="search",
                description="Search the shop for products matching keywords.",
                example_input='{"query": "blue running shoes size 10"}',
                fn=lambda args: self._step_once(f"search[{args.get('query','')}]"),
            ),
            ToolSpec(
                name="click",
                description="Click on a button or product link.",
                example_input='{"target": "B07X1G8N6Y"}',
                fn=lambda args: self._step_once(f"click[{args.get('target','')}]"),
            ),
        ]

    def observe(self) -> str:
        return f"Instruction: {self._instruction}\n\nPage:\n{self._last_obs}"

    def is_done(self) -> bool:
        return self._done

    def outcome(self) -> Outcome:
        # WebShop awards partial credit; we threshold at 1.0 for "success"
        # following standard practice.
        return Outcome(
            success=(self._reward >= 1.0),
            steps=self._step,
            reason=f"reward={self._reward:.3f}",
            benchmark_specific={"reward": float(self._reward)},
        )


class WebshopBenchmark(Benchmark):
    """WebShop instructions test split."""

    name = "webshop"

    def __init__(self, split: str = "test", max_steps: int = 25, limit: Optional[int] = None):
        self.split = split
        self.max_steps = max_steps
        self.limit = limit

    def _make_one(self):
        try:
            from web_agent_site.envs.web_agent_text_env import WebAgentTextEnv
        except ImportError as e:
            raise ImportError(
                "WebShop not installed. Either:\n"
                "  uv pip install webshop-minimal  (community subset)\n"
                "  OR clone https://github.com/princeton-nlp/WebShop and "
                "set WEBSHOP_PATH; then `pip install -e $WEBSHOP_PATH`.\n"
                f"Original error: {e}"
            ) from e
        return WebAgentTextEnv(observation_mode="text", num_products=None)

    def tasks(self) -> Iterator[Task]:
        env = self._make_one()
        # WebShop typically uses goals 0..500 for test
        n = self.limit or 500
        for i in range(n):
            env.reset(session=str(i))
            instruction = env.instruction_text
            yield Task(
                task_id=f"webshop_{i:04d}",
                description=instruction,
                metadata={"session": i},
            )

    def make_env(self, task: Task) -> Environment:
        env = self._make_one()
        env.reset(session=str(task.metadata["session"]))
        return _WebshopEnv(env, task.description, max_steps=self.max_steps)
