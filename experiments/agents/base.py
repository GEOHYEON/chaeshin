"""Common agent interface for the experimental harness.

Every system under evaluation (ReAct, Reflexion, Voyager-style, ADaPT,
Chaeshin variants) implements this interface. The runner only knows
this interface; it never imports a specific agent's internals.

The minimal contract:
    agent.run(env, openai_adapter, **opts) -> RunRecord
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StepRecord:
    """One Thought/Action/Observation step (or equivalent)."""
    step_idx: int
    thought: str = ""
    action: str = ""
    action_input: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    error: str = ""


@dataclass
class RunRecord:
    """Complete trace + outcome for one (agent, task, seed) trial."""
    agent_name: str
    benchmark_name: str
    task_id: str
    seed: int
    trial_idx: int = 0
    steps: List[StepRecord] = field(default_factory=list)
    final_answer: str = ""
    success: bool = False
    failure_reason: str = ""
    tokens_used: int = 0
    latency_seconds: float = 0.0
    # Per-system extension. Chaeshin uses this for case_ids retained etc.
    extras: Dict[str, Any] = field(default_factory=dict)


class Agent(abc.ABC):
    """Base class. Subclass + implement `name` and `run`."""

    name: str = "abstract"

    @abc.abstractmethod
    async def run(self, env, adapter, max_steps: int = 30) -> RunRecord:
        """Execute one trial on the given environment.

        Args:
            env: an Environment instance from a Benchmark
            adapter: an OpenAIAdapter (or compatible) for LLM calls
            max_steps: hard step cap; record terminates regardless

        Returns:
            A fully populated RunRecord.
        """
