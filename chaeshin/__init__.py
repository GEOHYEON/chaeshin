"""
Chaeshin (採薪) — Teach an agent to retrieve plans.

"Give an agent a plan, it solves one task.
 Teach it to retrieve plans, it solves them all."

A framework that retrieves, executes, and adapts
Tool Calling graphs from past successful cases
using Case-Based Reasoning.
"""

__version__ = "0.1.0"

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
