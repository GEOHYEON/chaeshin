"""GraphExecutor 테스트 — 그래프 실행, 조건 분기, 루프, 병렬."""

import asyncio
import json
import pytest

from chaeshin.schema import (
    GraphEdge,
    GraphNode,
    NodeStatus,
    ToolDef,
    ToolGraph,
    ToolParam,
)
from chaeshin.graph_executor import GraphExecutor


# ── 테스트용 도구 ──


async def exec_check(args: dict) -> str:
    flag = args.get("flag", False)
    return json.dumps({"ok": flag, "message": "checked"})


async def exec_analyze(args: dict) -> str:
    level = args.get("level", "HIGH")
    return json.dumps({"evidence_level": level, "result": "analyzed"})


async def exec_recommend(args: dict) -> str:
    return json.dumps({"recommendation": "do something", "completed": True})


async def exec_taste(args: dict) -> str:
    """간보기 — 호출 횟수에 따라 결과가 달라짐."""
    count = args.get("_call_count", 0)
    if count < 1:
        return json.dumps({"taste": "싱거움"})
    return json.dumps({"taste": "OK"})


TOOLS = {
    "check": ToolDef(
        name="check", description="체크", display_name="체크",
        category="test", executor=exec_check,
    ),
    "analyze": ToolDef(
        name="analyze", description="분석", display_name="분석",
        category="test", executor=exec_analyze,
    ),
    "recommend": ToolDef(
        name="recommend", description="권장", display_name="권장",
        category="test", executor=exec_recommend,
    ),
    "taste": ToolDef(
        name="taste", description="간보기", display_name="간보기",
        category="test", executor=exec_taste,
    ),
}


# ── 테스트 ──


class TestBasicExecution:
    @pytest.mark.asyncio
    async def test_linear_graph(self):
        """선형 그래프: n1 → n2 → n3."""
        graph = ToolGraph(
            nodes=[
                GraphNode(id="n1", tool="check", params_hint={"flag": True}),
                GraphNode(id="n2", tool="analyze"),
                GraphNode(id="n3", tool="recommend"),
            ],
            edges=[
                GraphEdge(from_node="n1", to_node="n2", condition="n1.output.ok == true"),
                GraphEdge(from_node="n2", to_node="n3"),
            ],
            entry_nodes=["n1"],
        )

        executor = GraphExecutor(tools=TOOLS)
        ctx = await executor.execute(graph)

        assert ctx.completed
        assert ctx.node_states["n1"].status == NodeStatus.DONE
        assert ctx.node_states["n2"].status == NodeStatus.DONE
        assert ctx.node_states["n3"].status == NodeStatus.DONE

    @pytest.mark.asyncio
    async def test_condition_branch_exit(self):
        """조건 분기: check 실패 시 exit."""
        graph = ToolGraph(
            nodes=[
                GraphNode(id="n1", tool="check", params_hint={"flag": False}),
                GraphNode(id="n2", tool="analyze"),
            ],
            edges=[
                GraphEdge(from_node="n1", to_node="n2", condition="n1.output.ok == true"),
                GraphEdge(from_node="n1", to_node=None, condition="n1.output.ok == false", action="emergency_exit"),
            ],
            entry_nodes=["n1"],
        )

        actions = []

        async def on_special(action, ctx):
            actions.append(action)

        executor = GraphExecutor(tools=TOOLS, on_special_action=on_special)
        ctx = await executor.execute(graph)

        assert ctx.completed
        assert ctx.special_action == "emergency_exit"
        assert ctx.node_states["n2"].status == NodeStatus.SKIPPED
        assert actions == ["emergency_exit"]


class TestParallelExecution:
    @pytest.mark.asyncio
    async def test_parallel_nodes(self):
        """병렬 실행: n1, n2 동시 → n3."""
        graph = ToolGraph(
            nodes=[
                GraphNode(id="n1", tool="check", params_hint={"flag": True}),
                GraphNode(id="n2", tool="analyze"),
                GraphNode(id="n3", tool="recommend"),
            ],
            edges=[
                GraphEdge(from_node="n1", to_node="n3"),
                GraphEdge(from_node="n2", to_node="n3"),
            ],
            parallel_groups=[["n1", "n2"]],
            entry_nodes=["n1", "n2"],
        )

        executor = GraphExecutor(tools=TOOLS)
        ctx = await executor.execute(graph)

        assert ctx.completed
        assert ctx.node_states["n1"].status == NodeStatus.DONE
        assert ctx.node_states["n2"].status == NodeStatus.DONE
        assert ctx.node_states["n3"].status == NodeStatus.DONE


class TestCallbacks:
    @pytest.mark.asyncio
    async def test_node_callbacks(self):
        """on_node_start, on_node_end 콜백 호출 확인."""
        started = []
        ended = []

        async def on_start(node, ctx):
            started.append(node.id)

        async def on_end(node, ctx, result):
            ended.append(node.id)

        graph = ToolGraph(
            nodes=[
                GraphNode(id="n1", tool="check", params_hint={"flag": True}),
                GraphNode(id="n2", tool="recommend"),
            ],
            edges=[GraphEdge(from_node="n1", to_node="n2")],
            entry_nodes=["n1"],
        )

        executor = GraphExecutor(
            tools=TOOLS,
            on_node_start=on_start,
            on_node_end=on_end,
        )
        await executor.execute(graph)

        assert "n1" in started
        assert "n2" in started
        assert "n1" in ended
        assert "n2" in ended

    @pytest.mark.asyncio
    async def test_patient_todo_callback(self):
        """환자 TODO 업데이트 콜백 확인."""
        todo_updates = []

        async def on_todo(items):
            todo_updates.append([i["status"] for i in items])

        graph = ToolGraph(
            nodes=[
                GraphNode(id="n1", tool="check", params_hint={"flag": True}),
                GraphNode(id="n2", tool="recommend"),
            ],
            edges=[GraphEdge(from_node="n1", to_node="n2")],
            entry_nodes=["n1"],
        )

        executor = GraphExecutor(
            tools=TOOLS,
            on_patient_todo_update=on_todo,
        )
        await executor.execute(graph)

        # 최소 3번 업데이트: 초기, n1 완료 후, n2 완료 후
        assert len(todo_updates) >= 3


class TestConditionEvaluation:
    def test_evaluate_basic_equality(self):
        """기본 == 조건 평가."""
        from chaeshin.schema import ExecutionContext, NodeState, NodeStatus

        ctx = ExecutionContext()
        ns = ctx.get_node_state("n1")
        ns.status = NodeStatus.DONE
        ns.output_data = {"ok": True}

        executor = GraphExecutor(tools={})

        assert executor._evaluate_condition("n1.output.ok == true", ctx) is True
        assert executor._evaluate_condition("n1.output.ok == false", ctx) is False

    def test_evaluate_inequality(self):
        """!= 조건 평가."""
        from chaeshin.schema import ExecutionContext, NodeState, NodeStatus

        ctx = ExecutionContext()
        ns = ctx.get_node_state("n1")
        ns.status = NodeStatus.DONE
        ns.output_data = {"level": "LOW"}

        executor = GraphExecutor(tools={})

        assert executor._evaluate_condition("n1.output.level != HIGH", ctx) is True
        assert executor._evaluate_condition("n1.output.level != LOW", ctx) is False

    def test_evaluate_none_condition(self):
        """condition이 None이면 항상 True."""
        from chaeshin.schema import ExecutionContext

        ctx = ExecutionContext()
        executor = GraphExecutor(tools={})

        assert executor._evaluate_condition(None, ctx) is True

    def test_evaluate_missing_node(self):
        """존재하지 않는 노드 참조 시 False."""
        from chaeshin.schema import ExecutionContext

        ctx = ExecutionContext()
        executor = GraphExecutor(tools={})

        assert executor._evaluate_condition("n999.output.field == value", ctx) is False
