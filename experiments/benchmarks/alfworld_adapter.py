"""ALFWorld adapter.

ALFWorld is a text-based household task environment with 134 unseen
test tasks. We use the textual variant (TextWorld backend).

Installation (one-time):
    uv pip install alfworld
    export ALFWORLD_DATA=~/.cache/alfworld
    alfworld-download   # ~2GB game data + scripts

Then `python -m experiments.runner --benchmark alfworld --agent react`
will iterate through the test split and produce JSONL logs.

References: Shridhar et al. ICLR 2021 (arXiv:2010.03768).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator, List, Optional

from experiments.benchmarks.base import Benchmark, Environment, Outcome, Task, ToolSpec


class _AlfworldEnv(Environment):
    """Wraps a single alfworld TextWorld game."""

    def __init__(self, alfworld_env, task_desc: str, max_steps: int = 30):
        self._env = alfworld_env
        self._task_desc = task_desc
        self._max_steps = max_steps
        self._step = 0
        self._done = False
        self._won = False
        self._last_observation: str = ""
        self._reset()

    def _reset(self):
        obs, info = self._env.reset()
        # alfworld returns list-wrapped obs/info for batched mode
        if isinstance(obs, list):
            obs = obs[0]
            info = {k: (v[0] if isinstance(v, list) else v) for k, v in info.items()}
        self._last_observation = obs
        self._info = info

    def _step_once(self, command: str) -> str:
        obs, reward, done, info = self._env.step([command])
        if isinstance(obs, list):
            obs = obs[0]
            done = done[0]
            info = {k: (v[0] if isinstance(v, list) else v) for k, v in info.items()}
        self._step += 1
        self._last_observation = obs
        self._info = info
        if done or self._step >= self._max_steps:
            self._done = True
            self._won = bool(info.get("won", False))
        return obs

    def tools(self) -> List[ToolSpec]:
        return [
            ToolSpec(
                name="act",
                description=(
                    "Send one ALFWorld text command to the environment "
                    "(e.g., 'go to kitchen 1', 'take apple 1 from countertop 2', "
                    "'put apple 1 in fridge 1', 'examine fridge 1', "
                    "'use sink 1', 'clean apple 1 with sink 1'). "
                    "Use ONE command per call."
                ),
                example_input='{"command": "go to kitchen 1"}',
                fn=lambda args: self._step_once(args.get("command", "look")),
            ),
        ]

    def observe(self) -> str:
        return f"Task: {self._task_desc}\n\nObservation:\n{self._last_observation}"

    def is_done(self) -> bool:
        return self._done

    def outcome(self) -> Outcome:
        return Outcome(
            success=self._won,
            steps=self._step,
            reason="won" if self._won else "step_limit_or_fail",
            benchmark_specific={
                "task_type": self._info.get("task_type", ""),
                "max_steps": self._max_steps,
            },
        )


class AlfworldBenchmark(Benchmark):
    """ALFWorld unseen test split."""

    name = "alfworld"

    def __init__(
        self,
        split: str = "eval_out_of_distribution",
        max_steps: int = 30,
        limit: Optional[int] = None,
    ):
        self.split = split
        self.max_steps = max_steps
        self.limit = limit

    def _get_loader(self):
        try:
            import alfworld.agents.environment as alf_envs
            import yaml
        except ImportError as e:
            raise ImportError(
                "ALFWorld not installed. Run:\n"
                "  uv pip install alfworld pyyaml\n"
                "  alfworld-download\n"
                f"Original error: {e}"
            ) from e
        config_path = os.path.join(
            os.environ.get("ALFWORLD_DATA", os.path.expanduser("~/.cache/alfworld")),
            "configs/base_config.yaml",
        )
        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"ALFWORLD config not found at {config_path}. "
                "Did you run `alfworld-download`?"
            )
        with open(config_path) as f:
            config = yaml.safe_load(f)
        env_type = config["env"]["type"]
        env_cls = getattr(alf_envs, env_type)
        env = env_cls(config, train_eval=self.split)
        env.seed(42)
        return env.init_env(batch_size=1), env

    def tasks(self) -> Iterator[Task]:
        env, _ = self._get_loader()
        n = self.limit or 134
        for i in range(n):
            obs, info = env.reset()
            if isinstance(obs, list):
                obs = obs[0]
                info = {k: (v[0] if isinstance(v, list) else v) for k, v in info.items()}
            task_desc = info.get("extra.gamefile", f"task_{i}")
            yield Task(
                task_id=f"alfworld_{i:04d}",
                description=str(task_desc),
                metadata={"task_type": info.get("task_type", "")},
            )

    def make_env(self, task: Task) -> Environment:
        # Re-create per task — alfworld auto-advances on reset.
        env, _ = self._get_loader()
        # Skip ahead to the right task index parsed from task_id
        idx = int(task.task_id.split("_")[-1])
        for _ in range(idx):
            env.reset()
        return _AlfworldEnv(env, task.description, max_steps=self.max_steps)
