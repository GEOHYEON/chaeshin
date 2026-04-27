"""Mock benchmark — no external dependencies, for harness smoke-testing.

Three toy ``find the key, open the door'' tasks. An agent that calls
the right sequence of tools succeeds; anything else fails after the
step limit. Useful to verify the pipeline end-to-end (agent loop,
metrics, aggregation) before installing ALFWorld/WebShop/τ-bench.

Run:
    uv run python -m experiments.runner --benchmark mock --agent react --seeds 0
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional

from experiments.benchmarks.base import Benchmark, Environment, Outcome, Task, ToolSpec


_TASKS = [
    {
        "task_id": "mock_0000",
        "description": "Find the key under the rug, then open the door.",
        "key_location": "rug",
        "needs": ["look_under(rug)", "pick_up(key)", "open(door)"],
    },
    {
        "task_id": "mock_0001",
        "description": "The key is in the drawer. Use it on the door.",
        "key_location": "drawer",
        "needs": ["open(drawer)", "pick_up(key)", "open(door)"],
    },
    {
        "task_id": "mock_0002",
        "description": "Find a key (could be in rug or drawer), open the door.",
        "key_location": "rug",
        "needs": ["look_under(rug)", "pick_up(key)", "open(door)"],
    },
]


class _MockEnv(Environment):
    def __init__(self, task_dict: Dict[str, Any], max_steps: int = 10):
        self._t = task_dict
        self._max = max_steps
        self._step = 0
        self._actions: List[str] = []
        self._has_key = False
        self._opened = False
        self._done = False

    def _record(self, action: str) -> str:
        self._actions.append(action)
        self._step += 1

        if action == "look_under(rug)":
            if self._t["key_location"] == "rug":
                obs = "Under the rug: a brass key."
            else:
                obs = "Under the rug: nothing."
        elif action == "open(drawer)":
            if self._t["key_location"] == "drawer":
                obs = "Drawer is open. Inside: a brass key."
            else:
                obs = "Drawer is open. Empty."
        elif action == "pick_up(key)":
            # Allow pick-up only if key was just visible
            last = self._actions[-2] if len(self._actions) >= 2 else ""
            if (last == "look_under(rug)" and self._t["key_location"] == "rug") or \
               (last == "open(drawer)" and self._t["key_location"] == "drawer"):
                self._has_key = True
                obs = "You picked up the key."
            else:
                obs = "There is no key here to pick up."
        elif action == "open(door)":
            if self._has_key:
                self._opened = True
                self._done = True
                obs = "The door swings open. Task complete."
            else:
                obs = "The door is locked."
        else:
            obs = f"Unknown action: {action}"

        if self._step >= self._max:
            self._done = True
        return obs

    def tools(self) -> List[ToolSpec]:
        return [
            ToolSpec("look_under", "Look under an object.",
                     '{"object": "rug"}',
                     lambda args: self._record(f"look_under({args.get('object','')})")),
            ToolSpec("open", "Open a container or door.",
                     '{"target": "drawer"}',
                     lambda args: self._record(f"open({args.get('target','')})")),
            ToolSpec("pick_up", "Pick up an item.",
                     '{"item": "key"}',
                     lambda args: self._record(f"pick_up({args.get('item','')})")),
        ]

    def observe(self) -> str:
        return f"Task: {self._t['description']}\n\nYou are in a small room with a rug, a drawer, and a door."

    def is_done(self) -> bool:
        return self._done

    def outcome(self) -> Outcome:
        return Outcome(
            success=self._opened,
            steps=self._step,
            reason="opened" if self._opened else "step_limit",
            benchmark_specific={"actions": list(self._actions)},
        )


class MockBenchmark(Benchmark):
    name = "mock"

    def __init__(self, max_steps: int = 10, limit: Optional[int] = None):
        self.max_steps = max_steps
        self.limit = limit

    def tasks(self) -> Iterator[Task]:
        n = self.limit or len(_TASKS)
        for t in _TASKS[:n]:
            yield Task(task_id=t["task_id"], description=t["description"], metadata=t)

    def make_env(self, task: Task) -> Environment:
        return _MockEnv(task.metadata, max_steps=self.max_steps)
