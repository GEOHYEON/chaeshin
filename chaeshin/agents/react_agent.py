"""ReAct 에이전트 — Chaeshin 메모리가 붙은 Thought/Action/Observation 루프.

자연스러운 ReAct 포맷:

    Thought: <사고>
    Action: <tool_name>
    Action Input: <JSON>

    (에이전트가 실행 후 다음 턴에 다음을 주입:)
    Observation: <결과>

    ... 반복 ...

    Final Answer: <최종 요약>

작업 시작 전 chaeshin_retrieve를 먼저 돌리도록 시스템 프롬프트로 강제하고,
작업을 끝낼 때 chaeshin_retain으로 실행한 그래프를 저장하게 한다.

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
    ):
        self.adapter = adapter
        self.tools = tools
        self.system_hint = system_hint
        self.max_steps = max_steps
        self.verbose = verbose

    # ── Prompt ────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        tool_block = []
        for spec in self.tools.values():
            tool_block.append(
                f"- {spec.name}: {spec.description}\n  example input: {spec.example_input}"
            )
        tools_text = "\n".join(tool_block)

        return f"""{self.system_hint}

당신은 지속적 기억(Chaeshin)이 붙은 에이전트입니다.

[규칙]
1. 작업을 시작하기 **전에 반드시** `chaeshin_retrieve`를 먼저 호출해서 비슷한 과거 케이스를 확인합니다.
   - `successes`가 있으면 그 그래프를 참고하세요.
   - `warnings`가 있으면 그 패턴은 피하세요 (실패로 기록된 것들).
2. 작업을 **끝낼 때 반드시** `chaeshin_retain`으로 당신이 실제 실행한 그래프를 저장합니다. 저장된 케이스는 `pending` 상태입니다. 성공/실패 판정은 사용자가 나중에 내립니다.
3. 출력 형식은 아래를 엄격히 지키세요:

Thought: <당신의 간결한 사고>
Action: <tool 이름 — 위 목록에서 하나>
Action Input: <한 줄 JSON>

실행 후 시스템이 다음을 덧붙입니다:

Observation: <tool 실행 결과>

Thought → Action → Observation을 반복하다가 작업이 끝나면 이렇게 종료:

Final Answer: <사용자에게 돌려줄 요약>

[사용 가능한 도구]
{tools_text}

[중요]
- 한 메시지에 Thought / Action / Action Input 한 세트만 내세요. 여러 개 내지 마세요.
- Action Input은 반드시 유효한 JSON 한 줄.
- 최종 답은 `Final Answer:` 로 시작합니다."""

    # ── Parsing ───────────────────────────────────────────────────────

    _ACTION_RE = re.compile(r"Action:\s*([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
    _INPUT_RE = re.compile(r"Action Input:\s*(\{.*?\})(?:\n|$)", re.DOTALL)
    _FINAL_RE = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)

    @classmethod
    def _parse(cls, text: str) -> Dict[str, Any]:
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
        spec = self.tools.get(name)
        if spec is None:
            return {"error": f"unknown tool '{name}'. 사용 가능: {list(self.tools)}"}
        try:
            result = spec.fn(args)
            if hasattr(result, "__await__"):
                result = await result
            return result
        except Exception as exc:
            logger.exception("tool_failed", tool=name)
            return {"error": f"tool '{name}' raised: {exc!r}"}

    # ── Main loop ─────────────────────────────────────────────────────

    async def run(self, user_request: str) -> Trace:
        system_prompt = self._build_system_prompt()
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_request},
        ]
        trace = Trace()

        if self.verbose:
            _print_banner("USER REQUEST", user_request)

        for step in range(self.max_steps):
            text = await self.adapter.llm_fn(messages)
            if self.verbose:
                _print_step(step + 1, text)

            parsed = self._parse(text)
            kind = parsed["kind"]

            if kind == "final":
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
            result = await self._run_tool(tool, args)
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
            messages.append({
                "role": "user",
                "content": f"Observation: {observation_text}",
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
    bar = "═" * 68
    print(f"\n{_CYAN}{bar}\n  {title}\n{bar}{_RESET}")
    if body:
        print(body)


def _print_step(n: int, text: str):
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
    lines = text.split("\n")
    preview = "\n".join(lines[:8])
    if len(lines) > 8:
        preview += f"\n{_DIM}  ... ({len(lines) - 8} more lines){_RESET}"
    print(f"{_GREEN}Observation:{_RESET} {preview}")


def _format_observation(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, indent=2)
    except TypeError:
        return str(result)
