"""Planner-free ReAct runtime and memory-observation contract tests."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List

from chaeshin.agents.react_agent import ReActAgent, ToolSpec
from chaeshin.case_store import CaseStore
from chaeshin.event_log import EventLog
from chaeshin.schema import (
    Case,
    CaseMetadata,
    GraphEdge,
    GraphNode,
    Outcome,
    ProblemFeatures,
    Solution,
    ToolGraph,
)
from examples._react_common import chaeshin_tools


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ScriptedAdapter:
    """Return deterministic model messages and retain each prompt snapshot."""

    def __init__(self, responses: Iterable[str]):
        self._responses = iter(responses)
        self.calls: List[List[Dict[str, str]]] = []

    async def llm_fn(self, messages: List[Dict[str, str]]) -> str:
        self.calls.append(deepcopy(messages))
        return next(self._responses)


def _action(name: str, args: Dict[str, Any]) -> str:
    payload = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
    return f"Thought: 다음 행동을 검증한다.\nAction: {name}\nAction Input: {payload}"


def _tool(name: str, fn) -> ToolSpec:
    return ToolSpec(name=name, description=f"{name} test tool", example_input="{}", fn=fn)


def test_importing_react_path_does_not_load_planner_module():
    """The primary ReAct import must not activate the legacy Planner path."""
    env = dict(os.environ)
    old_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(PROJECT_ROOT), old_pythonpath) if part
    )
    code = (
        "import sys\n"
        "from chaeshin.agents.react_agent import ReActAgent\n"
        "assert ReActAgent is not None\n"
        "assert 'chaeshin.planner' not in sys.modules, sorted("
        "m for m in sys.modules if m.startswith('chaeshin'))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_first_action_must_be_retrieve_and_attempted_domain_tool_is_not_run():
    domain_calls: List[Dict[str, Any]] = []
    retrieve_calls: List[Dict[str, Any]] = []
    adapter = ScriptedAdapter([
        _action("cook", {"minutes": 10}),
        _action("chaeshin_retrieve", {"query": "김치찌개 끓이는 법"}),
        "Final Answer: 검색 근거로 조리법을 설명했습니다.",
    ])
    tools = {
        "chaeshin_retrieve": _tool(
            "chaeshin_retrieve",
            lambda args: retrieve_calls.append(args) or {"successes": []},
        ),
        "cook": _tool("cook", lambda args: domain_calls.append(args) or {"ok": True}),
    }
    agent = ReActAgent(adapter, tools, system_hint="test", verbose=False)

    trace = asyncio.run(agent.run("김치찌개 끓이는 법 알려줘"))

    assert domain_calls == []
    assert retrieve_calls == [{"query": "김치찌개 끓이는 법"}]
    assert trace.final_answer == "검색 근거로 조리법을 설명했습니다."
    assert trace.steps[0] == {
        "type": "protocol_error",
        "reason": "retrieve_required_before_action",
        "attempted_tool": "cook",
    }
    assert "첫 Action으로 chaeshin_retrieve" in adapter.calls[1][-1]["content"]


def test_information_only_request_can_finish_after_retrieve_without_retain():
    retrieve_calls: List[Dict[str, Any]] = []
    retain_calls: List[Dict[str, Any]] = []
    adapter = ScriptedAdapter([
        _action(
            "chaeshin_retrieve",
            {
                "query": "김치찌개 끓이는 법 알려줘",
                "intent": "procedure_explanation",
                "context": {"current_state": {"task_mode": "information_only"}},
            },
        ),
        "Final Answer: 김치와 돼지고기를 볶고 육수를 부어 끓이세요.",
    ])
    tools = {
        "chaeshin_retrieve": _tool(
            "chaeshin_retrieve",
            lambda args: retrieve_calls.append(args) or {"successes": []},
        ),
        "chaeshin_retain": _tool(
            "chaeshin_retain",
            lambda args: retain_calls.append(args) or {"status": "saved"},
        ),
    }
    agent = ReActAgent(adapter, tools, system_hint="test", verbose=False)

    trace = asyncio.run(agent.run("김치찌개 끓이는 법 알려줘"))

    assert len(retrieve_calls) == 1
    assert retain_calls == []
    assert trace.final_answer.startswith("김치와 돼지고기")
    assert [step["type"] for step in trace.steps] == ["action", "final"]
    assert adapter.calls[1][-1]["content"].startswith("MemoryObservation:")


def test_final_after_domain_actions_requires_matching_trace_retain():
    domain_calls: List[tuple[str, Dict[str, Any]]] = []
    retain_calls: List[Dict[str, Any]] = []
    prepare_args = {"items": ["김치", "돼지고기"]}
    simmer_args = {"minutes": 20}
    graph = {
        "entry_nodes": ["n1"],
        "nodes": [
            {"id": "n1", "tool": "prepare", "params_hint": prepare_args},
            {"id": "n2", "tool": "simmer", "params_hint": simmer_args},
        ],
        "edges": [{"from_node": "n1", "to_node": "n2"}],
        "parallel_groups": [],
        "max_loops": 0,
    }
    adapter = ScriptedAdapter([
        _action("chaeshin_retrieve", {"query": "김치찌개 만들어줘"}),
        _action("prepare", prepare_args),
        _action("simmer", simmer_args),
        "Final Answer: 조리가 끝났습니다.",
        _action(
            "chaeshin_retain",
            {"request": "김치찌개 만들어줘", "graph": graph},
        ),
        "Final Answer: 조리가 끝났고 실제 실행 기록을 저장했습니다.",
    ])
    tools = {
        "chaeshin_retrieve": _tool("chaeshin_retrieve", lambda args: {"successes": []}),
        "chaeshin_retain": _tool(
            "chaeshin_retain",
            lambda args: retain_calls.append(args) or {"status": "saved"},
        ),
        "prepare": _tool(
            "prepare",
            lambda args: domain_calls.append(("prepare", args)) or {"ok": True},
        ),
        "simmer": _tool(
            "simmer",
            lambda args: domain_calls.append(("simmer", args)) or {"ok": True},
        ),
    }
    agent = ReActAgent(adapter, tools, system_hint="test", verbose=False)

    trace = asyncio.run(agent.run("김치찌개 만들어줘"))

    assert domain_calls == [("prepare", prepare_args), ("simmer", simmer_args)]
    assert retain_calls == [{"request": "김치찌개 만들어줘", "graph": graph}]
    assert trace.final_answer.endswith("저장했습니다.")
    assert any(
        step.get("reason") == "retain_required_before_final"
        for step in trace.steps
    )
    assert "execution trace와 정확히 같은 graph" in adapter.calls[4][-1]["content"]


def test_invalid_retain_graph_is_rejected_before_store_tool_runs():
    retain_calls: List[Dict[str, Any]] = []
    actual_args = {"minutes": 20}
    invalid_graph = {
        "nodes": [{"id": "n1", "tool": "simmer", "params_hint": {"minutes": 99}}],
        "edges": [],
    }
    valid_graph = {
        "nodes": [{"id": "n1", "tool": "simmer", "params_hint": actual_args}],
        "edges": [],
        "parallel_groups": [],
    }
    adapter = ScriptedAdapter([
        _action("chaeshin_retrieve", {"query": "김치찌개 만들어줘"}),
        _action("simmer", actual_args),
        _action("chaeshin_retain", {"request": "김치찌개", "graph": invalid_graph}),
        _action("chaeshin_retain", {"request": "김치찌개", "graph": valid_graph}),
        "Final Answer: 완료했습니다.",
    ])
    tools = {
        "chaeshin_retrieve": _tool("chaeshin_retrieve", lambda args: {"successes": []}),
        "chaeshin_retain": _tool(
            "chaeshin_retain",
            lambda args: retain_calls.append(args) or {"status": "saved"},
        ),
        "simmer": _tool("simmer", lambda args: {"ok": True}),
    }
    agent = ReActAgent(adapter, tools, system_hint="test", verbose=False)

    trace = asyncio.run(agent.run("김치찌개 만들어줘"))

    assert retain_calls == [{"request": "김치찌개", "graph": valid_graph}]
    retain_steps = [
        step for step in trace.steps
        if step.get("type") == "action" and step.get("tool") == "chaeshin_retain"
    ]
    assert retain_steps[0]["observation"]["error"] == (
        "retain_graph_does_not_match_execution_trace"
    )
    assert "params_hint" in retain_steps[0]["observation"]["detail"]
    assert retain_steps[1]["observation"] == {"status": "saved"}


def test_chaeshin_retrieve_returns_search_profile_and_complete_tool_graph():
    nodes = [
        GraphNode(
            id=f"n{i}",
            tool=f"tool_{i}",
            params_hint={"step": i},
            note=f"step {i}",
            input_schema={"step": "integer"},
            output_schema={"ok": "boolean"},
        )
        for i in range(1, 8)
    ]
    edges = [
        GraphEdge(
            from_node=f"n{i}",
            to_node=f"n{i + 1}",
            condition=f"n{i}.output.ok == true",
            priority=i,
            note=f"advance {i}",
        )
        for i in range(1, 7)
    ]
    edges.extend([
        GraphEdge(
            from_node="n7",
            to_node="n6",
            condition="n7.output.retry == true",
            priority=8,
            note="retry once",
        ),
        GraphEdge(
            from_node="n1",
            to_node=None,
            condition="n1.output.missing == true",
            action="ask_user",
            priority=0,
            note="request missing ingredient",
        ),
    ])
    case = Case(
        problem_features=ProblemFeatures(
            request="김치찌개 2인분 조리",
            category="cooking",
            keywords=["김치찌개", "조리법"],
            constraints=["돼지고기 사용"],
            context={
                "intent": "execute_recipe",
                "current_state": {"servings": 2},
            },
        ),
        solution=Solution(tool_graph=ToolGraph(
            nodes=nodes,
            edges=edges,
            parallel_groups=[["n1", "n2"]],
            entry_nodes=["n1"],
            max_loops=2,
        )),
        outcome=Outcome(
            status="success",
            result_summary="2인분 완성",
            tools_executed=7,
            loops_triggered=1,
            user_satisfaction=0.95,
            verdict_note="맛있어요",
            details={"servings": 2},
        ),
        metadata=CaseMetadata(
            case_id="kimchi-case-v3",
            source="test-fixture",
            version=3,
            root_case_id="kimchi-case-root",
            revision_index=2,
            used_count=4,
            avg_satisfaction=0.9,
            feedback_count=2,
            tags={"stable": 2},
        ),
    )
    store = CaseStore(embed_fn=lambda text: [1.0, float(bool(text))])
    store.retain(case)
    tools = chaeshin_tools(store, EventLog(), category="cooking", source="test")

    payload = tools["chaeshin_retrieve"].fn({
        "query": "김치찌개 끓이는 법 알려줘",
        "category": "cooking",
        "keywords": ["김치찌개", "조리법", "김치찌개"],
        "intent": "procedure_explanation",
        "goal": "초보자에게 순서 설명",
        "constraints": ["2인분", "안전 우선"],
        "context": {"audience": "beginner"},
        "current_state": {"task_mode": "information_only"},
        "blocking_unknowns": [],
        "optional_unknowns": ["맵기", "맵기"],
        "state_revision": 2,
        "reason": "user_changed_mode",
        "changed_fields": ["intent", "current_state.task_mode"],
        "previous_retrieval_id": "ret-before",
        "top_k": 5,
    })

    assert payload["kind"] == "chaeshin.memory_observation"
    assert payload["contract"]["role"] == "procedural_evidence_not_plan"
    assert payload["retrieval"]["mode"] == "hybrid"
    assert payload["retrieval"]["embedding_coverage"] == {
        "embedded_cases": 1,
        "candidate_cases": 1,
    }
    profile = payload["query_profile"]
    assert profile == {
        "query": "김치찌개 끓이는 법 알려줘",
        "category": "cooking",
        "keywords": ["김치찌개", "조리법"],
        "intent": "procedure_explanation",
        "goal": "초보자에게 순서 설명",
        "constraints": ["2인분", "안전 우선"],
        "context": {
            "audience": "beginner",
            "intent": "procedure_explanation",
            "goal": "초보자에게 순서 설명",
            "current_state": {"task_mode": "information_only"},
        },
        "blocking_unknowns": [],
        "optional_unknowns": ["맵기"],
        "state_revision": 2,
        "reason": "user_changed_mode",
        "changed_fields": ["intent", "current_state.task_mode"],
        "previous_retrieval_id": "ret-before",
    }

    assert payload["coverage"] == {
        "total_cases": 1,
        "returned_successes": 1,
        "returned_warnings": 0,
        "returned_pending": 0,
        "omitted": 0,
    }
    evidence = payload["successes"][0]
    assert evidence["case_id"] == "kimchi-case-v3"
    assert payload["contract"] == {
        "role": "procedural_reference_not_plan",
        "instruction": (
            "Use this evidence as reference when choosing the next Action; "
            "do not execute a graph merely because it ranks first."
        ),
    }
    assert evidence["usage"] == "reference_for_next_action"
    assert evidence["problem_features"] == {
        "request": "김치찌개 2인분 조리",
        "category": "cooking",
        "keywords": ["김치찌개", "조리법"],
        "constraints": ["돼지고기 사용"],
        "context": {
            "intent": "execute_recipe",
            "current_state": {"servings": 2},
        },
    }
    returned_graph = evidence["graph"]
    assert len(returned_graph["nodes"]) == 7
    assert returned_graph["nodes"][-1] == {
        "id": "n7",
        "tool": "tool_7",
        "params_hint": {"step": 7},
        "note": "step 7",
        "input_schema": {"step": "integer"},
        "output_schema": {"ok": "boolean"},
    }
    assert len(returned_graph["edges"]) == 8
    assert returned_graph["edges"][-1] == {
        "from_node": "n1",
        "to_node": None,
        "condition": "n1.output.missing == true",
        "action": "ask_user",
        "priority": 0,
        "note": "request missing ingredient",
    }
    assert returned_graph["parallel_groups"] == [["n1", "n2"]]
    assert returned_graph["entry_nodes"] == ["n1"]
    assert returned_graph["max_loops"] == 2
    assert evidence["outcome"] == {
        "status": "success",
        "result_summary": "2인분 완성",
        "tools_executed": 7,
        "loops_triggered": 1,
        "user_satisfaction": 0.95,
        "error_reason": "",
        "verdict_note": "맛있어요",
        "details": {"servings": 2},
    }
    assert evidence["provenance"] == {
        "source": "test-fixture",
        "version": 3,
        "root_case_id": "kimchi-case-root",
        "revision_index": 2,
        "updated_at": case.metadata.updated_at,
        "used_count": 4,
        "avg_satisfaction": 0.9,
        "feedback_count": 2,
        "tags": {"stable": 2},
    }


def test_embedding_failure_falls_back_to_lexical_and_reports_actual_mode():
    """Embedding 장애는 Case 적재/검색을 막지 않고 Observation에 드러나야 한다."""
    source = CaseStore()
    source.retain(Case(
        problem_features=ProblemFeatures(
            request="김치찌개 조리법",
            category="찌개류",
            keywords=["김치찌개"],
        ),
        solution=Solution(tool_graph=ToolGraph(
            nodes=[GraphNode(id="n1", tool="simmer")],
            entry_nodes=["n1"],
        )),
        outcome=Outcome(status="success"),
        metadata=CaseMetadata(case_id="fallback-case", source="test"),
    ))

    def unavailable_embedding(_text: str):
        raise RuntimeError("embedding service unavailable")

    store = CaseStore(embed_fn=unavailable_embedding)
    store.load_json(source.to_json())
    tools = chaeshin_tools(store, EventLog(), category="찌개류")

    payload = tools["chaeshin_retrieve"].fn({
        "query": "김치찌개 끓이는 법 알려줘",
        "keywords": ["김치찌개"],
    })

    assert payload["retrieval"]["mode"] == "lexical_fallback"
    assert payload["retrieval"]["embedding_coverage"] == {
        "embedded_cases": 0,
        "candidate_cases": 1,
    }
    assert payload["successes"][0]["case_id"] == "fallback-case"
