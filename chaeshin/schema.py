"""
Chaeshin Core Schema

CBR Case = (problem_features, solution, outcome, metadata)

- problem_features: 문제 정의 (사용자 요청, 재료, 제약 등)
- solution: Tool Graph (노드 + 엣지 — 실행 설계도)
- outcome: 실행 결과 (성공 여부, 만족도, 실행 시간 등)
- metadata: 케이스 관리 정보 (생성일, 사용 횟수, 버전 등)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════
# Tool Definition
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ToolParam:
    """도구 파라미터 정의."""

    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    items: Optional[Dict[str, str]] = None  # for array type
    default: Optional[Any] = None


@dataclass
class ToolDef:
    """도구 정의.

    도구는 그래프의 노드가 실행하는 함수.
    요리로 비유하면: 볶기, 끓이기, 썰기 같은 요리 동작.
    """

    name: str
    description: str
    display_name: str
    category: str
    params: List[ToolParam] = field(default_factory=list)
    executor: Optional[Callable[..., Coroutine]] = None

    def to_openai_tool(self) -> Dict[str, Any]:
        """OpenAI function calling 형식으로 변환."""
        properties = {}
        required = []
        for p in self.params:
            prop: Dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            if p.items:
                prop["items"] = p.items
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ═══════════════════════════════════════════════════════════════════════
# Tool Graph — 실행 설계도
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class GraphNode:
    """그래프 노드 — Tool Calling 한 단위.

    요리로 비유하면: "돼지고기+묵은지를 중불에서 5분 볶기" 같은 구체적 조리 단계.
    """

    id: str
    tool: str  # ToolDef.name 참조
    params_hint: Dict[str, Any] = field(default_factory=dict)
    note: str = ""  # 이 노드의 목적 설명 (예: "근거 반영 재분석")

    # input/output/state 스키마 — 런타임에 실행 컨텍스트에서 관리
    input_schema: Dict[str, str] = field(default_factory=dict)
    output_schema: Dict[str, str] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """그래프 엣지 — 노드 간 연결.

    condition이 있으면 조건부 분기.
    from_node → to_node가 None이면 특수 액션(emergency_exit, ask_user 등).
    루프도 가능 — from_node와 to_node가 역방향일 수 있음.

    요리로 비유하면: "간보기 → 싱거우면 → 다시 끓이기" 같은 흐름 제어.
    """

    from_node: str  # GraphNode.id
    to_node: Optional[str]  # GraphNode.id 또는 None (특수 액션)
    condition: Optional[str] = None  # 평가할 조건 (예: "n1.output.red_flag == false")
    action: Optional[str] = None  # to_node가 None일 때 실행할 특수 액션
    priority: int = 0  # 같은 from_node에서 여러 엣지가 있을 때 평가 우선순위
    note: str = ""


@dataclass
class ToolGraph:
    """Tool Calling 실행 그래프.

    DAG가 아닌 일반 그래프 — 루프(역방향 엣지)를 허용.
    요리로 비유하면: 레시피 전체.
    """

    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    parallel_groups: List[List[str]] = field(default_factory=list)  # 동시 실행 가능한 노드 그룹
    entry_nodes: List[str] = field(default_factory=list)  # 시작 노드 ID들
    max_loops: int = 3  # 무한 루프 방지

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_outgoing_edges(self, node_id: str) -> List[GraphEdge]:
        """특정 노드에서 나가는 엣지들 (priority 순 정렬)."""
        edges = [e for e in self.edges if e.from_node == node_id]
        return sorted(edges, key=lambda e: e.priority)

    def get_incoming_edges(self, node_id: str) -> List[GraphEdge]:
        """특정 노드로 들어오는 엣지들."""
        return [e for e in self.edges if e.to_node == node_id]


# ═══════════════════════════════════════════════════════════════════════
# CBR Case = (problem_features, solution, outcome, metadata)
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ProblemFeatures:
    """문제 정의 — CBR의 (problem_features).

    요리로 비유하면: "김치찌개 2인분, 묵은지 있음, 매운거 OK"
    """

    request: str  # 사용자 원본 요청
    category: str  # 문제 카테고리
    keywords: List[str] = field(default_factory=list)  # 핵심 키워드 (임베딩/검색용)
    constraints: List[str] = field(default_factory=list)  # 제약 조건
    context: Dict[str, Any] = field(default_factory=dict)  # 도메인별 추가 컨텍스트


@dataclass
class Solution:
    """실행 설계도 — CBR의 (solution).

    요리로 비유하면: 레시피 (썰기→볶기→끓이기→간보기)
    """

    tool_graph: ToolGraph = field(default_factory=ToolGraph)


@dataclass
class Outcome:
    """실행 결과 — CBR의 (outcome).

    요리로 비유하면: "김치찌개 2인분 완성, 35분 소요, 맛 평점 4.5"
    """

    success: bool = False
    result_summary: str = ""
    tools_executed: int = 0
    loops_triggered: int = 0
    total_time_ms: int = 0
    user_satisfaction: float = 0.0
    error_reason: str = ""  # 실패 사유 (success=False일 때)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseMetadata:
    """케이스 관리 정보 — CBR의 (metadata)."""

    case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    used_count: int = 0
    avg_satisfaction: float = 0.0
    source: str = "user_session"
    version: int = 1
    tags: List[str] = field(default_factory=list)


@dataclass
class Case:
    """CBR 케이스 — 최종 저장 단위.

    Case = (problem_features, solution, outcome, metadata)
    """

    problem_features: ProblemFeatures
    solution: Solution
    outcome: Outcome
    metadata: CaseMetadata = field(default_factory=CaseMetadata)


# ═══════════════════════════════════════════════════════════════════════
# Execution Context — 런타임 상태 (그래프는 불변, 이것만 가변)
# ═══════════════════════════════════════════════════════════════════════


class NodeStatus(Enum):
    """노드 실행 상태."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class NodeState:
    """개별 노드의 런타임 상태.

    그래프(설계도)는 안 바뀌고, 이 상태만 바뀜.
    요리로 비유하면: "볶기 노드 — 현재 실행 중, 재료: 돼지고기+묵은지"
    """

    node_id: str
    status: NodeStatus = NodeStatus.PENDING
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    loop_count: int = 0  # 이 노드가 루프로 몇 번 재실행됐는지


@dataclass
class ExecutionContext:
    """그래프 실행 컨텍스트 — 커서 위치 + 각 노드 상태.

    그래프(CBR Case의 solution.tool_graph)는 불변 설계도.
    이 컨텍스트만 실행 중에 변함.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    case_id: str = ""  # 어떤 CBR 케이스를 기반으로 실행 중인지
    node_states: Dict[str, NodeState] = field(default_factory=dict)
    current_nodes: List[str] = field(default_factory=list)  # 현재 실행 중인 노드(들)
    completed: bool = False
    special_action: Optional[str] = None  # emergency_exit, ask_user 등
    graph_version: int = 1  # 그래프가 LLM에 의해 수정되면 버전 증가
    history: List[Dict[str, Any]] = field(default_factory=list)  # 실행 이력

    def get_node_state(self, node_id: str) -> NodeState:
        if node_id not in self.node_states:
            self.node_states[node_id] = NodeState(node_id=node_id)
        return self.node_states[node_id]

    def record_event(self, event_type: str, node_id: str, data: Dict[str, Any] = None):
        """실행 이벤트 기록."""
        self.history.append({
            "event": event_type,
            "node_id": node_id,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
        })
