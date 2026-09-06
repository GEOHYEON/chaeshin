"""ReAct 에이전트 — Chaeshin 메모리가 붙은 Thought/Action/Observation 루프.

자연스러운 ReAct 포맷:

    Thought: <사고>
    Action: <tool_name>
    Action Input: <JSON>

    (에이전트가 실행 후 다음 턴에 다음을 주입:)
    Observation: <결과>

    ... 반복 ...

    Final Answer: <최종 요약>

작업 시작 전 chaeshin_retrieve를 먼저 돌리고, 검색된 과거 절차를 참고해 다음
행동 하나씩 선택한다. 도메인 도구를 실제 실행한 경우에만 chaeshin_retain으로
실제 실행 trace를 저장한다.

사용법:
    agent = ReActAgent(adapter=openai_adapter, tools={...}, system_hint="당신은 요리사입니다")
    final = await agent.run(user_request="김치찌개 2인분 해줘")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

import structlog

logger = structlog.get_logger(__name__)


Tool = Callable[[Dict[str, Any]], Union[Any, Awaitable[Any]]]


@dataclass
class ToolSpec:
    """에이전트에 노출할 도구 하나."""
    name: str
    description: str
    example_input: str
    fn: Tool


@dataclass
class Trace:
    """ReAct 실행 기록. 데모/디버깅용."""
    steps: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: str = ""


class ReActAgent:
    """Chaeshin 메모리를 쓰는 ReAct 에이전트.

    `tools`는 {이름: ToolSpec}. 반드시 `chaeshin_retrieve`, `chaeshin_retain`을
    포함해야 한다 (본인이 호출하도록 시스템 프롬프트에 박아둠).
    """

    def __init__(
        self,
        adapter,  # OpenAIAdapter
        tools: Dict[str, ToolSpec],
        system_hint: str,
        max_steps: int = 20,
        verbose: bool = True,
        enforce_actual_trace: bool = True,
    ):
        """LLM 어댑터, 도구 목록, 반복 상한과 콘솔 출력 정책을 설정한다."""
        self.adapter = adapter
        self.tools = tools
        self.system_hint = system_hint
        self.max_steps = max_steps
        self.verbose = verbose
        self.enforce_actual_trace = enforce_actual_trace

    # ── Prompt ────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """도구 명세와 Chaeshin 사용 규칙을 합쳐 시스템 프롬프트를 만든다."""
        tool_block = []
        for spec in self.tools.values():
            tool_block.append(
                f"- {spec.name}: {spec.description}\n  example input: {spec.example_input}"
            )
        tools_text = "\n".join(tool_block)
        if self.enforce_actual_trace:
            retain_policy = """5. 하나 이상의 도메인 도구를 실제 호출했다면 종료 전에
   `chaeshin_retain`을 호출하세요. 저장 그래프는 예상 계획이 아니라 실제
   execution trace와 정확히 같아야 합니다.
   - 실제 호출 1회마다 고유 node 1개. 재시도/루프도 각각 별도 node
   - node.tool은 실제 Action 이름, params_hint는 실제 Action Input
   - node.note에는 해당 호출의 실제 Observation 또는 실패를 짧게 요약
   - edge에는 실제 발생한 호출 순서만 기록
   - retain context에는 최신 retrieval_id, selected_case_ids, state_revision을 기록
   - 실행하지 않은 후보 분기나 미래 node를 넣지 않음
   - chaeshin_* 관리 도구는 실행 그래프에서 제외
   - outcome은 pending이며 성공/실패 verdict를 스스로 만들지 않음
   도메인 도구를 실행하지 않고 기억을 설명만 한 정보 제공 질문은 retain하지
   마세요. 기존 Case의 revise/verdict는 명시적인 사용자 근거가 있을 때만 합니다."""
        else:
            retain_policy = """5. 이 데모는 domain system hint가 명시한 memory-authoring
   절차를 따릅니다. 제안 ToolGraph를 retain할 수 있지만 항상 pending으로 저장하고,
   success/failure verdict는 스스로 만들지 마세요. 이 호환 모드는 일반 실행 trace
   저장용이 아니며, domain system hint에 없는 그래프를 발명하지 마세요."""

        return f"""{self.system_hint}

당신은 별도 Planner 없이 동작하는 단일 ReAct 정책 모델입니다.
Chaeshin은 실행 계획을 만드는 컴포넌트가 아니라 과거 절차 근거를 LLM Context로
제공하는 메모리입니다. 한 번에 다음 행동 하나만 결정하고
Thought → Action → Observation을 반복하세요.

[핵심 원칙]
1. 새 요청의 첫 Action은 반드시 `chaeshin_retrieve`입니다. 그 전에 전체 계획을
   만들지 마세요. 사용자 원문을 보존하면서 다음 검색 프로파일을 만드세요.
   - query, category, keywords
   - intent, goal, constraints
   - context.current_state: 실제로 알고 있는 상태만 기록
   - blocking_unknowns, optional_unknowns: 모르는 것은 false로 만들지 말고 분리
   - state_revision=0, reason="initial"
   임베딩과 hybrid score는 검색 도구가 계산하므로 직접 계산하지 마세요.

2. 검색된 ToolGraph는 과거 선례(evidence)이지 명령이나 확정 계획이 아닙니다.
   similarity 순위를 실행 순서로 해석하지 마세요. 후보의 ProblemFeatures, edge
   조건, 전체 ToolGraph, outcome, provenance와 현재 Observation을 함께 참고한 뒤,
   별도의 후보 판정 단계 없이 지금 호출할 다음 Tool 하나를 직접 선택하세요.
   `successes`는 과거에 잘된 절차 참고자료, `warnings`는 피해야 할 실패 패턴,
   `pending`은 아직 검증되지 않은 참고자료입니다. 메모리의 tool 이름이 현재 사용
   가능한 tool과 다르면 의미상 참고만 하고 그 이름을 직접 호출하지 마세요.

3. 실행 작업에서는 별도 Planner를 호출하거나 실행 전 고정된 전체 계획을
   확정하지 마세요. 현재 상태에서 안전한 다음 도메인 Action 하나만 선택합니다.
   사용자가 계획 자체를 산출물로 요청한 memory-authoring 작업은 예외입니다.
   조건이 관찰되기 전에는 해당 분기를 실행하지 않습니다.
   매 Observation을 최신 current_state에 반영하고, 도구 실패도 상태 변화로
   취급하세요.

4. 다음 변화가 후보 또는 필요한 그래프 구조를 바꿀 수 있으면 다음 도메인 Action
   전에 `chaeshin_retrieve`를 다시 호출하세요.
   - 사용자 목표/의도/hard constraint 변경
   - 안전, 알레르기, 권한, 재료, 자원 상태의 충돌 발견
   - 선택한 선례의 필수 전제가 거짓으로 확인됨
   - 도구 실패로 대체 절차가 필요하거나 필요한 분기/도구가 없음
   재검색에는 최신 current_state 전체, 증가한 state_revision,
   previous_retrieval_id, reason, changed_fields를 넣고 새 결과를 다음 Tool 선택에
   참고하세요.
   기존 그래프에 관찰값에 맞는 분기가 이미 있으면 불필요하게 재검색하지 마세요.

{retain_policy}

6. 정보 제공 요청이면 검색된 근거와 불확실성을 사람이 읽는 답으로 바꾸고
   종료하세요. blocking unknown을 관찰 도구로 해결할 수 없으면 필요한
   질문을 하세요. 기억이 없거나 검색이 실패해도 존재하지 않는 Case를 꾸미지
   말고 현재 도구와 도메인 규칙으로 진행하세요.

[출력 형식]
아래 형식을 엄격히 지키세요. Thought에는 숨은 장문 추론 대신 다음 행동을
검증할 수 있는 짧은 근거 한 문장만 씁니다.

Thought: <당신의 간결한 사고>
Action: <tool 이름 — 위 목록에서 하나>
Action Input: <한 줄 JSON>

실행 후 시스템이 다음을 덧붙입니다:

Observation: <tool 실행 결과>

Thought → Action → Observation을 반복하다가 작업이 끝나면 이렇게 종료:

Final Answer: <사용자에게 돌려줄 요약>

[사용 가능한 도구]
{tools_text}

[프로토콜]
- 한 메시지에 Thought / Action / Action Input 한 세트만 내세요. 여러 개 내지 마세요.
- Action Input은 반드시 유효한 JSON 한 줄.
- 최종 답은 `Final Answer:` 로 시작합니다."""

    @staticmethod
    def _is_domain_tool(name: str) -> bool:
        """Chaeshin 관리 도구가 아닌 실제 도메인 행동인지 판별한다."""
        return not name.startswith("chaeshin_")

    @staticmethod
    def _retain_validation_error(
        args: Dict[str, Any],
        execution_trace: List[Dict[str, Any]],
    ) -> Optional[str]:
        """retain graph가 실제 순차 실행 trace와 같은지 최소 불변식을 검사한다."""
        if not execution_trace:
            return "도메인 도구를 실행하지 않았으므로 저장할 execution trace가 없습니다."

        graph = args.get("graph")
        if not isinstance(graph, dict):
            return "graph 객체가 필요합니다."
        nodes = graph.get("nodes")
        edges = graph.get("edges", [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            return "graph.nodes와 graph.edges는 배열이어야 합니다."
        if len(nodes) != len(execution_trace):
            return (
                "graph.nodes 수가 실제 도메인 호출 수와 다릅니다: "
                f"expected={len(execution_trace)}, actual={len(nodes)}"
            )

        node_ids: List[str] = []
        for index, (node, actual) in enumerate(zip(nodes, execution_trace), start=1):
            if not isinstance(node, dict):
                return f"graph.nodes[{index - 1}]는 객체여야 합니다."
            node_id = str(node.get("id", "")).strip()
            if not node_id or node_id in node_ids:
                return "각 실행 node에는 서로 다른 비어 있지 않은 id가 필요합니다."
            node_ids.append(node_id)
            if node.get("tool") != actual["tool"]:
                return (
                    f"node {node_id}의 tool이 실제 호출과 다릅니다: "
                    f"expected={actual['tool']!r}, actual={node.get('tool')!r}"
                )
            if node.get("params_hint", {}) != actual["args"]:
                return f"node {node_id}의 params_hint가 실제 Action Input과 다릅니다."

        expected_edges = [
            (node_ids[index], node_ids[index + 1])
            for index in range(len(node_ids) - 1)
        ]
        actual_edges = []
        for edge in edges:
            if not isinstance(edge, dict):
                return "graph.edges의 각 항목은 객체여야 합니다."
            pair = (
                edge.get("from_node", edge.get("from")),
                edge.get("to_node", edge.get("to")),
            )
            actual_edges.append(pair)
        if actual_edges != expected_edges:
            return "graph.edges에는 실제로 발생한 순차 호출 연결만 정확히 기록해야 합니다."
        if graph.get("parallel_groups"):
            return "단일 ReAct 루프의 실제 순차 trace에는 parallel_groups를 넣지 마세요."
        return None

    # ── Parsing ───────────────────────────────────────────────────────

    _ACTION_RE = re.compile(r"Action:\s*([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
    _INPUT_RE = re.compile(r"Action Input:\s*(\{.*?\})(?:\n|$)", re.DOTALL)
    _FINAL_RE = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)

    @classmethod
    def _parse(cls, text: str) -> Dict[str, Any]:
        """LLM 텍스트를 최종 답변, 도구 호출, 형식 오류 중 하나로 분류한다.

        한 응답에 최종 답변과 액션이 함께 있으면 종료 의도를 우선한다.
        """
        final_match = cls._FINAL_RE.search(text)
        if final_match:
            return {"kind": "final", "answer": final_match.group(1).strip()}
        action = cls._ACTION_RE.search(text)
        if not action:
            return {"kind": "malformed", "raw": text}
        inp_match = cls._INPUT_RE.search(text)
        if not inp_match:
            return {"kind": "malformed", "raw": text}
        try:
            args = json.loads(inp_match.group(1))
        except json.JSONDecodeError as e:
            return {"kind": "bad_json", "error": str(e), "raw": inp_match.group(1)}
        return {"kind": "action", "tool": action.group(1), "args": args}

    # ── Execution ─────────────────────────────────────────────────────

    async def _run_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """동기·비동기 도구를 같은 경로로 실행하고 실패를 관찰값으로 바꾼다."""
        spec = self.tools.get(name)
        if spec is None:
            return {"error": f"unknown tool '{name}'. 사용 가능: {list(self.tools)}"}
        try:
            result = spec.fn(args)
            # ToolSpec은 동기 함수와 awaitable 반환 함수를 모두 허용한다.
            if hasattr(result, "__await__"):
                result = await result
            return result
        except Exception as exc:
            logger.exception("tool_failed", tool=name)
            return {"error": f"tool '{name}' raised: {exc!r}"}

    # ── Main loop ─────────────────────────────────────────────────────

    async def run(self, user_request: str) -> Trace:
        """Thought/Action/Observation을 반복해 실행 추적과 최종 답변을 반환한다."""
        system_prompt = self._build_system_prompt()
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request},
        ]
        trace = Trace()
        retrieved = False
        retained = False
        execution_trace: List[Dict[str, Any]] = []

        if self.verbose:
            _print_banner("USER REQUEST", user_request)

        for step in range(self.max_steps):
            text = await self.adapter.llm_fn(messages)
            if self.verbose:
                _print_step(step + 1, text)

            parsed = self._parse(text)
            kind = parsed["kind"]

            if kind == "final":
                if not retrieved:
                    trace.steps.append({
                        "type": "protocol_error",
                        "reason": "retrieve_required_before_final",
                    })
                    messages.append({"role": "assistant", "content": text})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Protocol Error: 첫 Action은 chaeshin_retrieve여야 합니다. "
                            "검색 프로파일을 만들어 먼저 호출하세요."
                        ),
                    })
                    continue
                if self.enforce_actual_trace and execution_trace and not retained:
                    trace.steps.append({
                        "type": "protocol_error",
                        "reason": "retain_required_before_final",
                    })
                    messages.append({"role": "assistant", "content": text})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Protocol Error: 실제 도메인 도구 호출이 있으므로 Final 전에 "
                            "그 execution trace와 정확히 같은 graph를 chaeshin_retain으로 "
                            "저장하세요."
                        ),
                    })
                    continue
                trace.final_answer = parsed["answer"]
                trace.steps.append({"type": "final", "text": text, "answer": parsed["answer"]})
                if self.verbose:
                    _print_banner("FINAL ANSWER", parsed["answer"])
                return trace

            if kind == "malformed":
                # 형식 어김 — 다시 유도
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": "출력이 규칙을 어겼습니다. Thought/Action/Action Input 형식으로 다시 내주세요.",
                })
                continue

            if kind == "bad_json":
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": f"Action Input이 유효한 JSON이 아닙니다 ({parsed['error']}). 한 줄 JSON으로 다시 내주세요.",
                })
                continue

            # 정상 Action
            tool = parsed["tool"]
            args = parsed["args"]
            if not retrieved and tool != "chaeshin_retrieve":
                trace.steps.append({
                    "type": "protocol_error",
                    "reason": "retrieve_required_before_action",
                    "attempted_tool": tool,
                })
                messages.append({"role": "assistant", "content": text})
                messages.append({
                    "role": "user",
                    "content": (
                        "Protocol Error: 이 Action은 실행하지 않았습니다. 첫 Action으로 "
                        "chaeshin_retrieve를 호출하세요."
                    ),
                })
                continue

            validation_error = None
            if tool == "chaeshin_retain" and self.enforce_actual_trace:
                validation_error = self._retain_validation_error(args, execution_trace)

            if validation_error:
                result = {
                    "error": "retain_graph_does_not_match_execution_trace",
                    "detail": validation_error,
                    "actual_execution_trace": [
                        {"tool": item["tool"], "args": item["args"]}
                        for item in execution_trace
                    ],
                }
            else:
                result = await self._run_tool(tool, args)

            if tool == "chaeshin_retrieve":
                # 검색 결과가 비어 있거나 일시적으로 실패해도 검색을 시도했다는
                # 사실은 충족된다. 이후 ReAct가 도메인 규칙으로 안전하게 저하한다.
                retrieved = True
            elif tool in self.tools and self._is_domain_tool(tool):
                execution_trace.append({"tool": tool, "args": args, "observation": result})
                # 저장 뒤 추가 행동을 했다면 최신 trace를 다시 저장해야 한다.
                retained = False
            elif tool == "chaeshin_retain" and not validation_error:
                retained = not (isinstance(result, dict) and result.get("error"))

            observation_text = _format_observation(result)

            trace.steps.append({
                "type": "action",
                "tool": tool,
                "args": args,
                "observation": result,
            })

            if self.verbose:
                _print_obs(observation_text)

            messages.append({"role": "assistant", "content": text})
            # 네이티브 tool role이 아닌 ReAct 텍스트 프로토콜이므로 관찰은 다음
            # 사용자 턴으로 주입해 모델이 후속 Thought/Action을 생성하게 한다.
            messages.append({
                "role": "user",
                "content": (
                    f"MemoryObservation: {observation_text}"
                    if tool == "chaeshin_retrieve"
                    else f"Observation: {observation_text}"
                ),
            })

        # 한도 초과
        trace.final_answer = "(max_steps reached — no final answer)"
        if self.verbose:
            _print_banner("WARNING", "max_steps 초과. 대화 종료.")
        return trace


# ── 콘솔 프린터 ───────────────────────────────────────────────────────

_RESET = "\033[0m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_MAGENTA = "\033[35m"


def _print_banner(title: str, body: str = ""):
    """콘솔에서 요청·결과 구간을 구분하는 배너를 출력한다."""
    bar = "═" * 68
    print(f"\n{_CYAN}{bar}\n  {title}\n{bar}{_RESET}")
    if body:
        print(body)


def _print_step(n: int, text: str):
    """ReAct 한 단계를 필드별 색상으로 구분해 출력한다."""
    print(f"\n{_DIM}── step {n} ──{_RESET}")
    for line in text.splitlines():
        if line.startswith("Thought:"):
            print(f"{_YELLOW}{line}{_RESET}")
        elif line.startswith("Action:"):
            print(f"{_MAGENTA}{line}{_RESET}")
        elif line.startswith("Action Input:"):
            print(f"{_MAGENTA}{line}{_RESET}")
        elif line.startswith("Final Answer:"):
            print(f"{_GREEN}{line}{_RESET}")
        else:
            print(line)


def _print_obs(text: str):
    """관찰값의 앞부분만 출력해 긴 도구 결과로 콘솔이 넘치지 않게 한다."""
    lines = text.split("\n")
    preview = "\n".join(lines[:8])
    if len(lines) > 8:
        preview += f"\n{_DIM}  ... ({len(lines) - 8} more lines){_RESET}"
    print(f"{_GREEN}Observation:{_RESET} {preview}")


def _format_observation(result: Any) -> str:
    """도구 결과를 모델에 다시 전달할 UTF-8 보존 문자열로 직렬화한다."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, indent=2)
    except TypeError:
        return str(result)
