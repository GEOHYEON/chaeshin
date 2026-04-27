"""Common benchmark interface.

Each benchmark wraps an external environment (ALFWorld, WebShop, τ-bench)
behind a uniform interface so agents can be swapped freely.

A benchmark exposes:
- `tasks()` — iterator of `Task` objects
- `make_env(task)` — returns an `Environment` for a single task
- `evaluate(env, action_log)` — returns `Outcome` after the agent finishes

The agent only ever sees `Environment.tools` and `Environment.observe()`;
this means the same agent code runs on any benchmark.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional


@dataclass
class Task:
    """One unit of evaluation."""
    task_id: str
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Outcome:
    """Per-trial outcome the harness records."""
    success: bool
    steps: int
    reason: str = ""
    benchmark_specific: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolSpec:
    """A tool the agent can call within this environment."""
    name: str
    description: str
    fn: Callable[[Dict[str, Any]], Any]
    example_input: str = "{}"


class Environment(abc.ABC):
    """Per-task environment. Lives only for the duration of one trial."""

    @abc.abstractmethod
    def tools(self) -> List[ToolSpec]:
        """Tools the agent can call. Returned at session start."""

    @abc.abstractmethod
    def observe(self) -> str:
        """Initial observation / problem statement passed to the agent."""

    @abc.abstractmethod
    def is_done(self) -> bool:
        """Whether the trial has terminated (success/failure/step-limit)."""

    @abc.abstractmethod
    def outcome(self) -> Outcome:
        """Compute outcome at end of trial."""


class Benchmark(abc.ABC):
    """Iterator over tasks + environment factory."""

    name: str = "abstract"

    @abc.abstractmethod
    def tasks(self) -> Iterator[Task]:
        """Yields all evaluation tasks."""

    @abc.abstractmethod
    def make_env(self, task: Task) -> Environment:
        """Create a fresh environment instance for the given task."""

    def __len__(self) -> int:
        # Default — override if cheaper.
        return sum(1 for _ in self.tasks())
