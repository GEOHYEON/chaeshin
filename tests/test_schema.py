"""Schema 테스트 — CBR Case, ToolGraph, ExecutionContext."""

import json
from dataclasses import asdict

from chaeshin.schema import (
    Case,
    CaseMetadata,
    ExecutionContext,
    GraphEdge,
    GraphNode,
    NodeState,
    NodeStatus,
    Outcome,
    ProblemFeatures,
    Solution,
    ToolDef,
    ToolGraph,
    ToolParam,
)


class TestToolDef:
    def test_to_openai_tool(self):
        tool = ToolDef(
            name="볶기",
            description="재료를 볶습니다",
            display_name="볶기",
            category="cooking",
            params=[
                ToolParam("재료", "string", "볶을 재료"),
                ToolParam("시간", "string", "조리 시간", required=False),
            ],
        )
        result = tool.to_openai_tool()

        assert result["type"] == "function"
        assert result["function"]["name"] == "볶기"
        assert "재료" in result["function"]["parameters"]["properties"]
        assert "재료" in result["function"]["parameters"]["required"]
        assert "시간" not in result["function"]["parameters"]["required"]


class TestToolGraph:
    def _make_graph(self) -> ToolGraph:
        return ToolGraph(
            nodes=[
                GraphNode(id="n1", tool="check"),
                GraphNode(id="n2", tool="analyze"),
                GraphNode(id="n3", tool="recommend"),
            ],
            edges=[
                GraphEdge(from_node="n1", to_node="n2", condition="n1.output.ok == true"),
                GraphEdge(from_node="n1", to_node=None, condition="n1.output.ok == false", action="exit"),
                GraphEdge(from_node="n2", to_node="n3"),
            ],
            entry_nodes=["n1"],
        )

    def test_get_node(self):
        graph = self._make_graph()
        assert graph.get_node("n1").tool == "check"
        assert graph.get_node("n2").tool == "analyze"
        assert graph.get_node("nonexistent") is None

    def test_get_outgoing_edges(self):
        graph = self._make_graph()
        edges = graph.get_outgoing_edges("n1")
        assert len(edges) == 2

    def test_get_incoming_edges(self):
        graph = self._make_graph()
        edges = graph.get_incoming_edges("n2")
        assert len(edges) == 1
        assert edges[0].from_node == "n1"

    def test_no_incoming_for_entry(self):
        graph = self._make_graph()
        edges = graph.get_incoming_edges("n1")
        assert len(edges) == 0


class TestCase:
    def test_case_creation(self):
        case = Case(
            problem_features=ProblemFeatures(
                request="김치찌개 만들어줘",
                category="찌개류",
                keywords=["김치", "찌개"],
            ),
            solution=Solution(
                tool_graph=ToolGraph(
                    nodes=[GraphNode(id="n1", tool="볶기")],
                    edges=[],
                ),
            ),
            outcome=Outcome(success=True, user_satisfaction=0.9),
            metadata=CaseMetadata(source="test"),
        )

        assert case.problem_features.request == "김치찌개 만들어줘"
        assert case.outcome.success is True
        assert len(case.solution.tool_graph.nodes) == 1

    def test_case_serialization(self):
        case = Case(
            problem_features=ProblemFeatures(
                request="테스트",
                category="test",
                keywords=["a", "b"],
            ),
            solution=Solution(tool_graph=ToolGraph()),
            outcome=Outcome(success=True),
        )
        data = asdict(case)
        json_str = json.dumps(data, ensure_ascii=False)
        parsed = json.loads(json_str)

        assert parsed["problem_features"]["request"] == "테스트"
        assert parsed["outcome"]["success"] is True


class TestExecutionContext:
    def test_node_state_management(self):
        ctx = ExecutionContext()
        ns = ctx.get_node_state("n1")

        assert ns.node_id == "n1"
        assert ns.status == NodeStatus.PENDING

        ns.status = NodeStatus.RUNNING
        assert ctx.get_node_state("n1").status == NodeStatus.RUNNING

    def test_record_event(self):
        ctx = ExecutionContext()
        ctx.record_event("test_event", "n1", {"key": "value"})

        assert len(ctx.history) == 1
        assert ctx.history[0]["event"] == "test_event"
        assert ctx.history[0]["node_id"] == "n1"
        assert ctx.history[0]["data"]["key"] == "value"
