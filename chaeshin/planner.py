"""
Graph Planner — LLM 기반 그래프 생성/수정.

1. 초기 계획: CBR에서 케이스 못 찾으면 LLM이 새 그래프 생성
2. 적응 (Adapt): CBR에서 찾은 그래프를 현재 상황에 맞게 수정
3. 리플래닝 (Replan): 실행 중 예외 발생 시 그래프를 diff로 수정

요리로 비유하면:
- 초기 계획: 레시피가 없어서 셰프가 즉석 창작
- 적응: 비슷한 레시피를 찾았는데, 재료가 좀 달라서 셰프가 수정
- 리플래닝: 요리 중 전화 와서 탔는데, 셰프가 복구 계획 수립
"""

from __future__ import annotations

import json
import structlog
from typing import Any, Callable, Coroutine, Dict, List, Optional

from chaeshin.schema import (
    ToolGraph,
    GraphNode,
    GraphEdge,
    ToolDef,
    ProblemFeatures,
    ExecutionContext,
    Case,
)

logger = structlog.get_logger(__name__)

# 그래프 생성용 시스템 프롬프트
CREATE_GRAPH_PROMPT = """당신은 Tool Calling 실행 그래프를 설계하는 전문가입니다.

사용 가능한 도구:
{tools_description}

사용자의 요청을 분석하여 Tool Graph를 JSON으로 설계하세요.

규칙:
1. nodes: 실행할 도구 노드들. 각 노드는 id, tool(도구 이름), params_hint(예상 파라미터), note(목적)를 가짐
2. edges: 노드 간 연결. from_node, to_node, condition(조건), action(특수액션), note를 가짐
3. parallel_groups: 동시 실행 가능한 노드 ID 그룹
4. 조건은 "노드ID.output.필드 == 값" 형식
5. to_node가 null이면 action에 특수 액션 명시 (emergency_exit, ask_user 등)
6. 루프가 필요하면 역방향 엣지로 표현
7. entry_nodes: 시작 노드 ID 목록

{reference_graph_section}

JSON만 출력하세요:
{{
  "nodes": [...],
  "edges": [...],
  "parallel_groups": [...],
  "entry_nodes": [...]
}}"""

ADAPT_GRAPH_PROMPT = """기존 Tool Graph를 현재 상황에 맞게 수정하세요.

기존 그래프:
{existing_graph}

현재 상황:
- 요청: {request}
- 제약: {constraints}
- 차이점: {differences}

수정된 전체 그래프를 JSON으로 출력하세요."""

REPLAN_GRAPH_PROMPT = """실행 중 예외가 발생했습니다. 그래프를 수정하세요.

현재 그래프:
{current_graph}

실행 상태:
{execution_state}

예외 사유:
{reason}

수정 방법을 JSON으로 출력하세요:
{{
  "added_nodes": [...],
  "removed_nodes": ["node_id", ...],
  "added_edges": [...],
  "removed_edges": [{{"from_node": "...", "to_node": "..."}}, ...],
  "updated_node_states": {{"node_id": "ready|skipped", ...}},
  "reasoning": "수정 이유"
}}"""


class GraphPlanner:
    """LLM 기반 그래프 생성/수정 플래너."""

    def __init__(
        self,
        llm_fn: Callable[[List[Dict[str, str]]], Coroutine[Any, Any, str]],
        tools: Dict[str, ToolDef],
        reference_graphs: Optional[List[ToolGraph]] = None,
    ):
        """
        Args:
            llm_fn: LLM 호출 함수. messages → response text
            tools: 사용 가능한 도구들
            reference_graphs: 참조할 그래프 패턴 (ClinicalStateGraph 등)
        """
        self.llm_fn = llm_fn
        self.tools = tools
        self.reference_graphs = reference_graphs or []

    async def create_graph(
        self,
        problem: ProblemFeatures,
    ) -> ToolGraph:
        """새 그래프를 처음부터 생성 (CBR에서 케이스 못 찾았을 때)."""
        tools_desc = self._format_tools()
        ref_section = self._format_reference_graphs()

        prompt = CREATE_GRAPH_PROMPT.format(
            tools_description=tools_desc,
            reference_graph_section=ref_section,
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": (
                f"요청: {problem.request}\n"
                f"카테고리: {problem.category}\n"
                f"키워드: {', '.join(problem.keywords)}\n"
                f"제약: {', '.join(problem.constraints)}\n"
                f"컨텍스트: {json.dumps(problem.context, ensure_ascii=False)}"
            )},
        ]

        response = await self.llm_fn(messages)
        return self._parse_graph(response)

    async def adapt_graph(
        self,
        case: Case,
        current_problem: ProblemFeatures,
    ) -> ToolGraph:
        """CBR에서 가져온 케이스의 그래프를 현재 상황에 맞게 수정."""
        existing = self._graph_to_dict(case.solution.tool_graph)

        # 차이점 분석
        differences = []
        prev = case.problem_features
        if prev.category != current_problem.category:
            differences.append(f"카테고리: {prev.category} → {current_problem.category}")
        old_kw = set(prev.keywords)
        new_kw = set(current_problem.keywords)
        if old_kw != new_kw:
            added = new_kw - old_kw
            removed = old_kw - new_kw
            if added:
                differences.append(f"추가된 키워드: {', '.join(added)}")
            if removed:
                differences.append(f"제거된 키워드: {', '.join(removed)}")

        if not differences:
            # 차이 없으면 그대로 사용
            return case.solution.tool_graph

        messages = [
            {"role": "system", "content": ADAPT_GRAPH_PROMPT.format(
                existing_graph=json.dumps(existing, ensure_ascii=False, indent=2),
                request=current_problem.request,
                constraints=", ".join(current_problem.constraints),
                differences="; ".join(differences),
            )},
        ]

        response = await self.llm_fn(messages)
        return self._parse_graph(response)

    async def replan_graph(
        self,
        graph: ToolGraph,
        ctx: ExecutionContext,
        reason: str,
    ) -> ToolGraph:
        """실행 중 예외 발생 시 그래프를 diff로 수정."""
        current = self._graph_to_dict(graph)
        exec_state = self._format_execution_state(ctx)

        messages = [
            {"role": "system", "content": REPLAN_GRAPH_PROMPT.format(
                current_graph=json.dumps(current, ensure_ascii=False, indent=2),
                execution_state=exec_state,
                reason=reason,
            )},
        ]

        response = await self.llm_fn(messages)

        try:
            diff = json.loads(self._extract_json(response))
            return self._apply_diff(graph, diff)
        except Exception as e:
            logger.error("replan_parse_error", error=str(e), response=response)
            return graph  # 파싱 실패 시 기존 그래프 유지

    def _apply_diff(self, graph: ToolGraph, diff: Dict[str, Any]) -> ToolGraph:
        """diff를 그래프에 적용."""
        import copy
        new_graph = copy.deepcopy(graph)

        # 노드 삭제
        removed_ids = set(diff.get("removed_nodes", []))
        new_graph.nodes = [n for n in new_graph.nodes if n.id not in removed_ids]

        # 엣지 삭제
        for re in diff.get("removed_edges", []):
            new_graph.edges = [
                e for e in new_graph.edges
                if not (e.from_node == re.get("from_node") and e.to_node == re.get("to_node"))
            ]

        # 노드 추가
        for nd in diff.get("added_nodes", []):
            new_graph.nodes.append(GraphNode(
                id=nd["id"],
                tool=nd["tool"],
                params_hint=nd.get("params_hint", {}),
                note=nd.get("note", ""),
            ))

        # 엣지 추가
        for ed in diff.get("added_edges", []):
            new_graph.edges.append(GraphEdge(
                from_node=ed["from"],
                to_node=ed.get("to"),
                condition=ed.get("condition"),
                action=ed.get("action"),
                note=ed.get("note", ""),
            ))

        logger.info(
            "diff_applied",
            added_nodes=len(diff.get("added_nodes", [])),
            removed_nodes=len(diff.get("removed_nodes", [])),
            added_edges=len(diff.get("added_edges", [])),
            removed_edges=len(diff.get("removed_edges", [])),
            reasoning=diff.get("reasoning", ""),
        )

        return new_graph

    # ── Helpers ────────────────────────────────────────────────────────

    def _format_tools(self) -> str:
        lines = []
        for name, tool in self.tools.items():
            params = ", ".join(
                f"{p.name}({p.type}{'*' if p.required else ''})"
                for p in tool.params
            )
            lines.append(f"- {name}: {tool.description} [{params}]")
        return "\n".join(lines)

    def _format_reference_graphs(self) -> str:
        if not self.reference_graphs:
            return ""

        parts = ["참조 그래프 패턴 (이 순서를 참고하세요):"]
        for i, g in enumerate(self.reference_graphs):
            nodes = " → ".join(n.tool for n in g.nodes)
            parts.append(f"  패턴 {i + 1}: {nodes}")
        return "\n".join(parts)

    @staticmethod
    def _graph_to_dict(graph: ToolGraph) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(graph)

    def _format_execution_state(self, ctx: ExecutionContext) -> str:
        lines = []
        for nid, ns in ctx.node_states.items():
            line = f"  {nid}: status={ns.status.value}"
            if ns.output_data:
                line += f", output={json.dumps(ns.output_data, ensure_ascii=False)}"
            if ns.error:
                line += f", error={ns.error}"
            lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _extract_json(text: str) -> str:
        """텍스트에서 JSON 부분만 추출."""
        # ```json ... ``` 블록 찾기
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        # { ... } 찾기
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group(0)
        return text

    @staticmethod
    def _parse_graph(response: str) -> ToolGraph:
        """LLM 응답에서 ToolGraph 파싱."""
        json_str = GraphPlanner._extract_json(response)
        data = json.loads(json_str)

        nodes = [
            GraphNode(
                id=n["id"],
                tool=n["tool"],
                params_hint=n.get("params_hint", {}),
                note=n.get("note", ""),
            )
            for n in data.get("nodes", [])
        ]

        edges = [
            GraphEdge(
                from_node=e["from"] if "from" in e else e.get("from_node", ""),
                to_node=e.get("to") or e.get("to_node"),
                condition=e.get("condition"),
                action=e.get("action"),
                note=e.get("note", ""),
            )
            for e in data.get("edges", [])
        ]

        return ToolGraph(
            nodes=nodes,
            edges=edges,
            parallel_groups=data.get("parallel_groups", []),
            entry_nodes=data.get("entry_nodes", []),
        )
