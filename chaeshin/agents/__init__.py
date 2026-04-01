"""
Chaeshin Agents — 에이전트 런타임 레이어.

claw-code(Claude Code)의 에이전트 아키텍처를 참고한 구현:
- Orchestrator: queryLoop 패턴의 대화 루프
- SubagentManager: AgentTool/runAgent 패턴의 서브에이전트 관리
- DecomposerAgent: 계층적 태스크 분해
- ExecutorAgent: 레이어별 실행 + 체크포인트
- ReflectionAgent: 피드백 → 그래프 변환
"""

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
]
