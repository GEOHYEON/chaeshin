"""
BaseAgent + SubagentManager — 에이전트 기반 클래스 + 서브에이전트 관리.

claw-code 참고:
- AgentTool.tsx: 서브에이전트 생성, prompt/subagent_type/isolation 지정
- runAgent.ts: 에이전트 실행 라이프사이클 (init → register → query loop → finalize)
- InProcessTeammateTask: 같은 프로세스 내 격리된 에이전트 실행
- SendMessageTool: 실행 중인 에이전트에 메시지 전달
"""

from __future__ import annotations

import uuid
import asyncio
import structlog
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Coroutine, Dict, List, Optional

logger = structlog.get_logger(__name__)


class AgentStatus(Enum):
    """에이전트 상태 — claw-code의 Task 상태와 동일."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class AgentResult:
    """에이전트 실행 결과 — claw-code의 AgentResult 참고."""
    agent_id: str
    agent_type: str
    status: AgentStatus = AgentStatus.COMPLETED
    output: Any = None
    error: Optional[str] = None
    started_at: str = ""
    finished_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentContext:
    """에이전트 실행 컨텍스트 — 부모로부터 상속받는 정보."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_agent_id: Optional[str] = None
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    shared_state: Dict[str, Any] = field(default_factory=dict)
    available_tools: Dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """에이전트 기반 클래스.

    claw-code의 QueryEngine + query.ts queryLoop 패턴:
    - run()이 AsyncGenerator로 중간 진행 상황을 yield
    - 서브에이전트는 SubagentManager를 통해 spawn
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        agent_type: str = "base",
        llm_fn: Optional[Callable[[List[Dict[str, str]]], Coroutine[Any, Any, str]]] = None,
        context: Optional[AgentContext] = None,
    ):
        self.agent_id = agent_id or str(uuid.uuid4())
        self.agent_type = agent_type
        self.llm_fn = llm_fn
        self.context = context or AgentContext()
        self.status = AgentStatus.PENDING
        self._started_at: Optional[str] = None
        self._finished_at: Optional[str] = None

    @abstractmethod
    async def run(self, prompt: str, **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """에이전트 실행 — AsyncGenerator로 중간 결과를 yield.

        claw-code의 queryLoop 패턴:
        while not done:
            1. LLM 호출 (또는 도구 실행)
            2. yield 중간 결과 (progress, tool_result, checkpoint 등)
            3. 완료/에러 시 return

        Args:
            prompt: 실행할 태스크 설명

        Yields:
            진행 상황 딕셔너리:
            - {"type": "progress", "message": "...", "data": {...}}
            - {"type": "checkpoint", "layer": "L2", "results": [...]}
            - {"type": "result", "output": {...}}
            - {"type": "error", "error": "..."}
        """
        yield {}  # type: ignore

    async def execute(self, prompt: str, **kwargs) -> AgentResult:
        """run()을 감싸는 편의 메서드 — 최종 결과만 반환.

        중간 진행을 무시하고 최종 AgentResult만 필요할 때 사용.
        """
        self.status = AgentStatus.RUNNING
        self._started_at = datetime.now().isoformat()
        output = None
        error = None

        try:
            async for event in self.run(prompt, **kwargs):
                if event.get("type") == "result":
                    output = event.get("output")
                elif event.get("type") == "error":
                    error = event.get("error")
                    self.status = AgentStatus.FAILED
                    break
            if self.status != AgentStatus.FAILED:
                self.status = AgentStatus.COMPLETED
        except Exception as e:
            error = str(e)
            self.status = AgentStatus.FAILED
            logger.error("agent_execution_error", agent_id=self.agent_id, error=error)

        self._finished_at = datetime.now().isoformat()

        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=self.status,
            output=output,
            error=error,
            started_at=self._started_at,
            finished_at=self._finished_at,
        )

    async def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """LLM 호출 헬퍼."""
        if not self.llm_fn:
            raise RuntimeError(f"Agent {self.agent_id}: llm_fn이 설정되지 않음")
        return await self.llm_fn(messages)


class SubagentManager:
    """서브에이전트 관리자.

    claw-code 참고:
    - AgentTool: spawn(agent_type, prompt) → AgentResult
    - SendMessageTool: send_message(agent_id, message) → response
    - InProcessTeammateTask: 같은 프로세스 내 실행
    - spawnMultiAgent: 팀 단위 에이전트 관리

    Orchestrator가 이 매니저를 통해 서브에이전트를 생성/관리.
    """

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._results: Dict[str, AgentResult] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def spawn(
        self,
        agent: BaseAgent,
        prompt: str,
        background: bool = False,
        **kwargs,
    ) -> AgentResult:
        """서브에이전트를 생성하고 실행.

        claw-code의 AgentTool.call() 패턴:
        1. 에이전트 등록
        2. 프롬프트로 실행
        3. 결과 반환 (background=True면 즉시 반환)

        Args:
            agent: 실행할 에이전트 인스턴스
            prompt: 태스크 설명
            background: True면 백그라운드 실행 (즉시 반환)
            **kwargs: 에이전트별 추가 인자
        """
        self._agents[agent.agent_id] = agent

        logger.info(
            "subagent_spawned",
            agent_id=agent.agent_id,
            agent_type=agent.agent_type,
            background=background,
        )

        if background:
            task = asyncio.create_task(agent.execute(prompt, **kwargs))
            self._running_tasks[agent.agent_id] = task
            return AgentResult(
                agent_id=agent.agent_id,
                agent_type=agent.agent_type,
                status=AgentStatus.RUNNING,
            )

        result = await agent.execute(prompt, **kwargs)
        self._results[agent.agent_id] = result

        logger.info(
            "subagent_completed",
            agent_id=agent.agent_id,
            status=result.status.value,
        )

        return result

    async def spawn_streaming(
        self,
        agent: BaseAgent,
        prompt: str,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """서브에이전트를 생성하고 스트리밍 실행.

        run()의 중간 결과를 그대로 전달.
        Orchestrator가 유저에게 진행 상황을 보여줄 때 사용.
        """
        self._agents[agent.agent_id] = agent
        agent.status = AgentStatus.RUNNING

        try:
            async for event in agent.run(prompt, **kwargs):
                yield {
                    "agent_id": agent.agent_id,
                    "agent_type": agent.agent_type,
                    **event,
                }
        except Exception as e:
            yield {
                "agent_id": agent.agent_id,
                "agent_type": agent.agent_type,
                "type": "error",
                "error": str(e),
            }

    async def send_message(self, agent_id: str, message: str) -> Optional[str]:
        """실행 중인 에이전트에 메시지 전달.

        claw-code의 SendMessageTool 패턴.
        현재 구현: 에이전트의 context에 메시지를 추가.
        """
        agent = self._agents.get(agent_id)
        if not agent:
            logger.warning("agent_not_found", agent_id=agent_id)
            return None

        agent.context.conversation_history.append({
            "role": "user",
            "content": message,
        })
        return f"Message sent to {agent_id}"

    async def get_result(self, agent_id: str) -> Optional[AgentResult]:
        """백그라운드 에이전트의 결과 조회."""
        if agent_id in self._results:
            return self._results[agent_id]

        task = self._running_tasks.get(agent_id)
        if task and task.done():
            result = task.result()
            self._results[agent_id] = result
            del self._running_tasks[agent_id]
            return result

        return None

    async def kill(self, agent_id: str) -> bool:
        """에이전트 강제 종료."""
        task = self._running_tasks.get(agent_id)
        if task and not task.done():
            task.cancel()
            agent = self._agents.get(agent_id)
            if agent:
                agent.status = AgentStatus.KILLED
            logger.info("agent_killed", agent_id=agent_id)
            return True
        return False

    def list_agents(self) -> List[Dict[str, Any]]:
        """현재 등록된 에이전트 목록."""
        return [
            {
                "agent_id": a.agent_id,
                "agent_type": a.agent_type,
                "status": a.status.value,
            }
            for a in self._agents.values()
        ]
