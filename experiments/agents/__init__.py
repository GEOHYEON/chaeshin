"""Agent registry."""

from experiments.agents.base import Agent, RunRecord, StepRecord
from experiments.agents.react_agent import ReActAgent
from experiments.agents.reflexion_agent import ReflexionAgent
from experiments.agents.voyager_style_agent import VoyagerStyleAgent
from experiments.agents.adapt_agent import AdaptAgent
from experiments.agents.chaeshin_agent import (
    ChaeshinFullAgent, ChaeshinNoCascadeAgent,
    ChaeshinNoPendingAgent, ChaeshinNoRecursionAgent,
)


_REGISTRY = {
    "react":                 ReActAgent,
    "reflexion":             ReflexionAgent,
    "voyager_style":         VoyagerStyleAgent,
    "adapt":                 AdaptAgent,
    "chaeshin_full":         ChaeshinFullAgent,
    "chaeshin_no_cascade":   ChaeshinNoCascadeAgent,
    "chaeshin_no_pending":   ChaeshinNoPendingAgent,
    "chaeshin_no_recursion": ChaeshinNoRecursionAgent,
}


def get_agent(name: str) -> Agent:
    name = name.lower()
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"unknown agent {name!r}. Available: {sorted(_REGISTRY)}")
    return cls()


def list_agents():
    return sorted(_REGISTRY)


__all__ = ["Agent", "RunRecord", "StepRecord", "get_agent", "list_agents"]
