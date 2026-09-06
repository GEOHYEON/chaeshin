"""Chaeshin Agents — 에이전트 런타임 레이어.

기본 공개 경로는 별도 Planner가 없는 ReActAgent다. 아래 기존 에이전트들은
호환성을 위해 이름을 유지하지만 실제로 요청될 때만 lazy import한다.

claw-code(Claude Code)의 에이전트 아키텍처를 참고한 legacy 구현:
- Orchestrator: queryLoop 패턴의 대화 루프
- SubagentManager: AgentTool/runAgent 패턴의 서브에이전트 관리
- DecomposerAgent: 계층적 태스크 분해
- ExecutorAgent: 레이어별 실행 + 체크포인트
- ReflectionAgent: 피드백 → 그래프 변환
"""

from typing import TYPE_CHECKING

from chaeshin.agents.react_agent import ReActAgent, ToolSpec, Trace

if TYPE_CHECKING:
    from chaeshin.agents.base import BaseAgent, SubagentManager, AgentResult, AgentStatus
    from chaeshin.agents.orchestrator import OrchestratorAgent
    from chaeshin.agents.decomposer import DecomposerAgent
    from chaeshin.agents.executor_agent import ExecutorAgent
    from chaeshin.agents.reflection import ReflectionAgent

__all__ = [
    "BaseAgent",
    "SubagentManager",
    "AgentResult",
    "AgentStatus",
    "OrchestratorAgent",
    "DecomposerAgent",
    "ExecutorAgent",
    "ReflectionAgent",
    "ReActAgent",
    "ToolSpec",
    "Trace",
]


_LEGACY_EXPORTS = {
    "BaseAgent": ("chaeshin.agents.base", "BaseAgent"),
    "SubagentManager": ("chaeshin.agents.base", "SubagentManager"),
    "AgentResult": ("chaeshin.agents.base", "AgentResult"),
    "AgentStatus": ("chaeshin.agents.base", "AgentStatus"),
    "OrchestratorAgent": ("chaeshin.agents.orchestrator", "OrchestratorAgent"),
    "DecomposerAgent": ("chaeshin.agents.decomposer", "DecomposerAgent"),
    "ExecutorAgent": ("chaeshin.agents.executor_agent", "ExecutorAgent"),
    "ReflectionAgent": ("chaeshin.agents.reflection", "ReflectionAgent"),
}


def __getattr__(name: str):
    """legacy agent를 사용할 때만 해당 모듈과 Planner 의존성을 로드한다."""
    target = _LEGACY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
