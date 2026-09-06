"""
Chaeshin (採薪) — Procedural memory context for ReAct agents.

"Store procedural evidence once; let ReAct reuse it in the right state."

A framework that retrieves success, failure, and pending ToolGraph evidence
for a host LLM using Case-Based Reasoning.

The primary agent path is planner-free ReAct.  ``GraphPlanner`` and
``TaskTree`` remain lazy legacy exports for backwards compatibility.
"""

__version__ = "0.1.0"

from typing import TYPE_CHECKING

from chaeshin.schema import (
    ToolDef,
    ToolParam,
    GraphNode,
    GraphEdge,
    ToolGraph,
    ProblemFeatures,
    Solution,
    Outcome,
    CaseMetadata,
    Case,
    ExecutionContext,
    NodeState,
)
from chaeshin.graph_executor import GraphExecutor
from chaeshin.case_store import CaseStore

if TYPE_CHECKING:
    from chaeshin.planner import GraphPlanner, TaskTree

__all__ = [
    # Schema
    "ToolDef",
    "ToolParam",
    "GraphNode",
    "GraphEdge",
    "ToolGraph",
    "ProblemFeatures",
    "Solution",
    "Outcome",
    "CaseMetadata",
    "Case",
    "ExecutionContext",
    "NodeState",
    # Core
    "GraphExecutor",
    "CaseStore",
    "GraphPlanner",
    "TaskTree",
]


def __getattr__(name: str):
    """기존 Planner API는 요청된 경우에만 로드해 ReAct 경로와 분리한다."""
    if name in {"GraphPlanner", "TaskTree"}:
        from chaeshin import planner as planner_module

        value = getattr(planner_module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Optional integrations — import 실패해도 코어에 영향 없음
try:
    from chaeshin.integrations.openai import OpenAIAdapter
    __all__.append("OpenAIAdapter")
except ImportError:
    pass

try:
    from chaeshin.integrations.chroma import ChromaCaseStore
    __all__.append("ChromaCaseStore")
except ImportError:
    pass

try:
    from chaeshin.integrations.weaviate import WeaviateCaseStore
    __all__.append("WeaviateCaseStore")
except ImportError:
    pass
