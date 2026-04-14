# Chaeshin v2 — 에이전트 아키텍처 & 업그레이드 명세

> v1: flat한 Tool Graph 저장/검색
> v2: 계층적 분해 + 레이어별 Graph + 피드백 반영 에이전트

---

## 1. 전체 흐름

```
유저 질문
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                 Decomposer Agent                         │
│                                                         │
│  1) 질문을 3~5개 하위 태스크로 분해                       │
│  2) 각 태스크가 Tool Call 가능할 때까지 재귀 분해          │
│  3) 분해 깊이로 난이도(difficulty) 산출                   │
│  4) 난이도 or 피드백 많은 영역 → chaeshin_retrieve        │
│  5) 분해 트리 + 검색된 케이스 → Executor에 전달           │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 Executor Agent                           │
│                                                         │
│  1) 분해 트리의 최하위(L1)부터 Tool Call 실행             │
│  2) 레이어 완료 시 유저에게 체크포인트 보고               │
│  3) 실행 중 예외 → Planner에 replan 위임                 │
│  4) 전체 실행 완료 → 결과 반환                           │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 Reflection Agent                         │
│                                                         │
│  1) 유저 피드백 수신 (자연어)                             │
│  2) 피드백이 어느 레이어에 해당하는지 자동 판단            │
│  3) 해당 레이어의 Graph를 수정/분할/승격                  │
│  4) chaeshin_retain으로 업데이트된 케이스 저장             │
│  5) 필요 시 difficulty 재산정                             │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 에이전트별 상세 설계

### 2-1. Decomposer Agent (분해 에이전트)

**역할:** 유저 질문을 계층적 태스크 트리로 분해하고, Chaeshin 조회 여부를 결정한다.

**입력:**
- 유저 자연어 질문
- 사용 가능한 Tool 목록

**출력:**
- 분해 트리 (TaskTree)
- 난이도 점수 (difficulty)
- Chaeshin에서 가져온 참조 케이스 (있으면)

**핵심 로직:**

```python
def decompose(question, tools, chaeshin_store):
    # 1단계: 질문을 3~5개 하위 태스크로 분해
    subtasks = llm_decompose(question, max_children=5)

    # 2단계: 각 하위 태스크가 tool로 직접 실행 가능한지 판단
    for task in subtasks:
        if is_tool_callable(task, tools):
            task.layer = "L1"  # 최하위, tool call 매핑
        else:
            task.children = decompose(task, tools, chaeshin_store)  # 재귀

    # 3단계: 트리 깊이 = difficulty
    difficulty = max_depth(subtasks)

    # 4단계: Chaeshin 조회 판단
    if difficulty >= 2 or has_high_feedback_area(question, chaeshin_store):
        cases = chaeshin_retrieve(question)
        merge_cases_into_tree(subtasks, cases)

    return TaskTree(subtasks, difficulty)
```

**Chaeshin 조회 트리거 (두 축):**

| 조건 | 설명 |
|---|---|
| `difficulty >= 2` | 분해가 2단계 이상 필요한 복잡한 질문 |
| `feedback_count >= 3` | 해당 영역에 유저 피드백이 3회 이상 누적 |

**Span 규칙:**

| 레이어 | 하위 노드 수 | 근거 |
|---|---|---|
| 최상위 (전략) | 3~5개 | Span of Control 상위 (복잡) |
| 중간 (패턴) | 5~7개 | Miller's Law 중간 |
| 최하위 (실행) | 7~15개 tool call | Span of Control 하위 (단순) |

---

### 2-2. Executor Agent (실행 에이전트)

**역할:** 분해 트리를 받아서 최하위부터 실제 Tool Call을 실행한다.

**입력:**
- TaskTree (Decomposer가 만든 분해 트리)
- 참조 케이스의 Graph (있으면)

**출력:**
- 실행 결과
- 실행 경로 로그 (Retention용)

**핵심 로직:**

```python
async def execute(task_tree):
    # 최하위 레이어(L1)부터 실행
    for layer in task_tree.bottom_up():
        for task in layer.tasks:
            if task.is_tool_callable():
                result = await execute_tool(task.tool, task.params)
                task.result = result
            else:
                # 하위 태스크 결과를 종합
                task.result = aggregate(task.children)

        # 레이어 완료 → 유저에게 체크포인트
        checkpoint(layer)
```

**기존 코드와의 관계:**
- `graph_executor.py`의 `GraphExecutor`를 확장
- 현재 flat한 그래프 실행 → 계층적 트리 실행으로 변경
- `on_replan` 콜백은 그대로 활용 (예외 시 LLM 위임)

**체크포인트:**
- 각 레이어 완료 시 유저에게 중간 결과 보고
- 유저가 "여기서 방향 바꿔" 하면 → Reflection Agent로 전달

---

### 2-3. Reflection Agent (반영 에이전트)

**역할:** 유저 피드백을 해석하고, 해당 레이어의 Graph를 수정하여 Chaeshin에 저장한다.

**입력:**
- 유저 피드백 (자연어)
- 현재 실행 중인 TaskTree

**출력:**
- 수정된 Graph (chaeshin_retain)
- 난이도 재산정 결과

**핵심 로직:**

```python
def reflect(feedback, task_tree, chaeshin_store):
    # 1단계: 피드백이 어느 레이어에 해당하는지 판단
    target_layer, target_node = classify_feedback(feedback, task_tree)

    # 2단계: 피드백 유형 판단
    feedback_type = analyze_feedback_type(feedback)

    if feedback_type == "ESCALATE":
        # "이건 더 복잡해" → 레이어 높이기
        escalate_layer(target_node, task_tree, chaeshin_store)

    elif feedback_type == "MODIFY":
        # "순서 바꿔" → 해당 레이어 Graph 수정
        modify_graph(target_node, feedback, chaeshin_store)

    elif feedback_type == "SIMPLIFY":
        # "이건 한번에 해도 돼" → 레이어 낮추기
        simplify_layer(target_node, task_tree, chaeshin_store)

    # 3단계: 수정된 케이스 저장
    chaeshin_retain(modified_case)

    # 4단계: difficulty 재산정
    recalculate_difficulty(task_tree)
```

**피드백 유형 분류:**

| 유형 | 예시 | 동작 |
|---|---|---|
| ESCALATE | "자료수집이 이렇게 단순하지 않아" | 기존 Graph를 한 레벨 아래로 밀고, 새 중간 레이어 생성 |
| MODIFY | "수면 질문을 먼저 해" | 해당 레이어의 Graph에서 노드 순서/엣지 수정 |
| SIMPLIFY | "이건 한번에 해도 돼" | 하위 레이어를 상위로 병합 (레이어 제거) |
| CORRECT | "이 툴 대신 저걸 써" | L1 Graph에서 tool 노드 교체 |
| REJECT | "이건 아예 안 해도 돼" | 해당 노드 제거 + 엣지 재연결 |

**ESCALATE 상세 동작 (레이어 높이기):**

```
Before:
  L2 자료수집: [일정리뷰] → [이슈추출] → [진행률] → [미완료] → [일정확인]

피드백: "팀별로 나눠서 수집해야 하고, 외부 데이터도 봐야 해"

After:
  L2 자료수집 (새): [내부데이터수집] → [외부데이터수집] → [팀별취합] → [검증]
  L1 내부데이터수집 (기존→강등): [일정리뷰] → [이슈추출] → [진행률] → [미완료] → [일정확인]
  L1 외부데이터수집 (새): [경쟁사뉴스] → [시장데이터] → [업계리포트]
```

데이터 변경:
1. 기존 케이스의 `layer` 필드를 L2→L1로 변경
2. 새 L2 케이스 생성 (피드백 내용으로)
3. 새 L1 케이스 생성 (새로 추가된 하위 태스크)
4. 전체 `difficulty` +1

---

## 3. Chaeshin v2 스키마 변경

### 3-1. Case 스키마 확장

```python
@dataclass
class CaseMetadata:
    # === 기존 필드 (유지) ===
    case_id: str
    created_at: str
    updated_at: str
    used_count: int
    avg_satisfaction: float
    source: str
    version: int
    tags: List[str]

    # === v2 신규 필드 ===
    layer: str = ""              # "L1", "L2", "L3", ... (빈 문자열이면 flat/레거시)
    parent_case_id: str = ""     # 상위 레이어 케이스 ID
    parent_node_id: str = ""     # 상위 케이스에서 이 케이스에 대응하는 노드 ID
    difficulty: int = 0          # 이 케이스를 루트로 할 때의 분해 깊이
    feedback_count: int = 0      # 유저 피드백 누적 횟수
    feedback_log: List[str] = field(default_factory=list)  # 피드백 이력 요약
    child_case_ids: List[str] = field(default_factory=list)  # 하위 레이어 케이스 IDs
```

### 3-2. MCP Tool 변경

#### `chaeshin_retain` 확장

```python
@mcp.tool()
def chaeshin_retain(
    request: str,
    graph: dict,
    # === 기존 파라미터 (유지) ===
    category: str = "",
    keywords: str = "",
    summary: str = "",
    satisfaction: float = 0.85,
    success: bool = True,
    error_reason: str = "",
    # === v2 신규 파라미터 ===
    layer: str = "",               # "L1", "L2", "L3", ...
    parent_case_id: str = "",      # 상위 케이스 ID
    parent_node_id: str = "",      # 상위 노드 ID
    difficulty: int = 0,           # 분해 깊이
) -> str:
```

#### `chaeshin_retrieve` 확장

```python
@mcp.tool()
def chaeshin_retrieve(
    query: str,
    # === 기존 파라미터 (유지) ===
    category: str = "",
    keywords: str = "",
    top_k: int = 3,
    # === v2 신규 파라미터 ===
    include_children: bool = False,   # True면 하위 레이어 케이스도 함께 반환
    include_parent: bool = False,     # True면 상위 레이어 케이스도 함께 반환
    min_feedback_count: int = 0,      # 피드백 N회 이상인 케이스만
) -> str:
```

#### `chaeshin_feedback` 신규

```python
@mcp.tool()
def chaeshin_feedback(
    case_id: str,                    # 피드백 대상 케이스
    feedback: str,                   # 유저 피드백 (자연어)
    feedback_type: str = "auto",     # "escalate", "modify", "simplify", "correct", "reject", "auto"
) -> str:
    """유저 피드백을 Chaeshin 케이스에 반영한다.

    feedback_type="auto"면 LLM이 피드백 유형을 자동 판단.
    Reflection Agent가 내부적으로 호출.
    """
```

#### `chaeshin_decompose` 신규

```python
@mcp.tool()
def chaeshin_decompose(
    query: str,                      # 유저 질문
    tools: str = "",                 # 사용 가능한 tool 목록 (comma-separated)
    max_depth: int = 4,              # 최대 분해 깊이
) -> str:
    """질문을 계층적 태스크 트리로 분해한다.

    Decomposer Agent가 내부적으로 호출.
    분해 + 난이도 산출 + Chaeshin 조회를 한 번에 수행.

    Returns:
        task_tree (JSON), difficulty, matched_cases
    """
```

---

## 4. 기존 코드 영향 분석

| 파일 | 변경 내용 |
|---|---|
| `schema.py` | `CaseMetadata`에 v2 필드 추가 (하위 호환) |
| `case_store.py` | `retrieve`에 parent/children 연쇄 로드 로직 추가, `feedback` 메서드 추가 |
| `mcp_server.py` | `chaeshin_feedback`, `chaeshin_decompose` 추가, 기존 tool 파라미터 확장 |
| `planner.py` | `create_graph` → `create_tree` 확장 (계층적 분해) |
| `graph_executor.py` | flat 실행 → 레이어별 실행 지원 (체크포인트 추가) |

### 하위 호환성

- `layer`, `parent_case_id` 등 v2 필드는 모두 기본값이 빈 문자열/0
- 기존 17개 케이스는 `layer=""` (flat/레거시)로 취급
- 기존 `chaeshin_retain`/`chaeshin_retrieve` 호출은 그대로 동작
- v2 기능은 새 파라미터를 명시적으로 전달할 때만 활성화

---

## 5. 레이어별 Graph 저장 예시

### "팀 위클리 미팅 준비" 전체 구조

```
chaeshin_retain(
  request="팀 위클리 미팅 준비 - 전체 전략",
  layer="L3",
  difficulty=3,
  graph={
    nodes: [
      {id: "s1", tool: "자료수집", note: "지난주 진행+이슈 종합"},
      {id: "s2", tool: "문서작성", note: "위클리 템플릿 채우기"},
      {id: "s3", tool: "팀원공유", note: "슬랙+사전리뷰"}
    ],
    edges: [{from: "s1", to: "s2"}, {from: "s2", to: "s3"}]
  },
  child_case_ids=["case-l2-자료수집", "case-l2-문서작성", "case-l2-팀원공유"]
)

chaeshin_retain(
  request="위클리 자료수집",
  layer="L2",
  parent_case_id="case-l3-위클리",
  parent_node_id="s1",
  graph={
    nodes: [
      {id: "p1", tool: "get_calendar", note: "지난주 일정 리뷰"},
      {id: "p2", tool: "read_email", note: "이슈/블로커 추출"},
      {id: "p3", tool: "analyze_data", note: "진행률"},
      {id: "p4", tool: "read_email", note: "미완료 액션아이템"},
      {id: "p5", tool: "get_calendar", note: "이번주 일정"}
    ],
    edges: [{from:"p1",to:"p2"}, {from:"p2",to:"p3"},
            {from:"p3",to:"p4"}, {from:"p4",to:"p5"}]
  }
)
```

### ESCALATE 피드백 후

```
chaeshin_feedback(
  case_id="case-l2-자료수집",
  feedback="팀별로 따로 수집해야 하고 외부 데이터도 봐야 해",
  feedback_type="escalate"
)

→ 결과:
  기존 L2 → L1으로 강등 (layer="L1", parent_node_id="내부데이터수집")
  새 L2 생성: [내부데이터수집] → [외부데이터수집] → [팀별취합] → [검증]
  새 L1 생성: [경쟁사뉴스] → [시장데이터] → [업계리포트]
  difficulty: 3 → 4
  feedback_count: 0 → 1
```

---

## 6. 검색(Retrieve) 동작 변경

### 기본 동작 (기존과 동일)

```
chaeshin_retrieve(query="위클리 준비 어떻게 해?")
→ 벡터 유사도로 매칭, 가장 유사한 케이스 반환
→ 쿼리가 추상적이면 L3가, 구체적이면 L1이 자연스럽게 1위
```

### v2 확장: 계층 연쇄 로드

```
chaeshin_retrieve(
  query="위클리 준비 어떻게 해?",
  include_children=True  # 하위 레이어도 함께
)

→ 1위: L3 "위클리 전략" (similarity: 0.66)
  + children:
    L2 "자료수집" (parent_node_id: s1)
    L2 "문서작성" (parent_node_id: s2)
    L2 "팀원공유" (parent_node_id: s3)
      + children:
        L1 "일정리뷰→이슈추출→..." (parent_node_id: p1)
        ...
```

### 피드백 가중치

```python
# retrieve 시 피드백 많은 케이스에 가중치
final_score = similarity * 0.7 + feedback_weight * 0.3

# feedback_weight = min(feedback_count / 10, 1.0)
# 피드백 10회 이상이면 최대 가중치
```

---

## 7. 자동 에스컬레이션 — 실행 중 레이어를 넘나드는 수정

<p align="center">
  <img src="../../assets/layered-execution.svg" alt="Layered Execution & Escalation — 요리 예시" width="820"/>
</p>

### 7-1. 문제 정의

사람은 전체 그림(L3)을 먼저 짜두고, 세부(L1)를 실행하면서 필요하면 윗단계까지 거슬러 올라가서 전략을 바꾼다. Chaeshin v2도 이렇게 동작해야 한다.

현재 문제: L1에서 replan이 실패해도 L1 안에서만 맴돌다 max_loops에 걸려 교착됨. Executor가 "위에 L2, L3가 있다"는 사실을 모르기 때문.

### 7-2. 에스컬레이션 흐름

```
L1 노드 실패
  │
  ▼
L1 replan 시도 (기존 로직 — LLM이 diff 생성)
  │
  ├─ 성공 → L1에서 계속 실행
  │
  └─ 실패 → LLM에 에스컬레이션 판단 요청
              (이때 L1 실행 로그 전체 + 상위 레이어 정보를 넘김)
              │
              ├─ LLM: "L1에서 해결 가능" → L1 replan 재시도 (다른 방법으로)
              │
              └─ LLM: "escalate to L2" → L2 체크포인트 강제 발동
                        │
                        ▼
                  L2 replan 시도 (L1 실패 로그 전체를 컨텍스트로 포함)
                        │
                        ├─ 성공 → L2에서 L1들을 재구성, 다시 실행
                        │
                        └─ 실패 → LLM에 에스컬레이션 판단 요청
                                    │
                                    └─ "escalate to L3" → L3 체크포인트 강제 발동
                                              │
                                              ├─ 성공 → L3에서 L2/L1을 재구성
                                              │
                                              └─ 실패 → special_action: "ask_user"
                                                         유저에게 전체 에스컬레이션 체인 보여줌
```

### 7-3. 에스컬레이션 페이로드 — 로그 전체 넘기기

L1이 여러 개일 때, 실패한 L1뿐 아니라 형제 노드의 상태도 함께 넘겨야 상위 레이어가 전체 상황을 판단할 수 있다.

```python
@dataclass
class EscalationPayload:
    """에스컬레이션 시 상위 레이어에 전달하는 정보."""

    escalated_from: str          # "L1"
    escalated_to: str            # "L2"

    failed: dict                 # 실패한 노드 상세
    # {
    #   "node": "L1-b",
    #   "status": "failed",
    #   "history": [...],          ← 실행 로그 전체 (ExecutionContext.history)
    #   "replan_attempts": [...]   ← L1에서 시도한 diff들
    # }

    completed_siblings: list     # 이미 성공한 형제 노드들
    # [
    #   {"node": "L1-a", "status": "success", "history": [...]},
    # ]

    pending_siblings: list       # 아직 실행 안 한 형제 노드들
    # ["L1-c", "L1-d"]
```

예시 — L2 "빌드 & 배포" 밑에 L1이 3개 있을 때:

```
L2: 빌드 & 배포
  ├── L1-a: git pull     ✅ (성공 로그 5줄)
  ├── L1-b: docker build ❌ (실패 로그 + replan 시도 2회 로그)
  └── L1-c: push image   ⏳ (아직 실행 안 함)

→ 에스컬레이션 페이로드:
  escalated_from: "L1"
  escalated_to: "L2"
  failed:
    node: "L1-b"
    history: [
      {event: "node_started", node_id: "n1", ...},
      {event: "node_failed", node_id: "n1", data: {error: "port 8080 conflict"}},
      {event: "replan_requested", data: {reason: "포트 충돌"}},
      {event: "node_started", node_id: "n1-fix", ...},   ← replan으로 추가된 노드
      {event: "node_failed", node_id: "n1-fix", data: {error: "port 8081 also in use"}},
    ]
    replan_attempts: [
      {diff: {added_nodes: [{id: "n1-fix", tool: "change_port"}]}, result: "failed"},
    ]
  completed_siblings:
    - {node: "L1-a", status: "success", history: [{...git pull 성공 로그...}]}
  pending_siblings: ["L1-c"]
```

### 7-4. L2 replan 프롬프트

상위 레이어가 에스컬레이션을 받았을 때, 아래 정보를 모두 포함해서 LLM에 replan을 요청한다:

```
[에스컬레이션 수신]
현재 레이어: L2 (빌드 & 배포)
현재 L2 그래프: {nodes, edges}

하위 레이어(L1) 실행 상황:
  ✅ L1-a (git pull): 성공
  ❌ L1-b (docker build): 실패
     - 실패 원인: 포트 8080, 8081 모두 충돌
     - 시도한 수정: 포트 변경 (2회 실패)
     - 전체 로그: [...]
  ⏳ L1-c (push image): 미실행

→ L2 수준에서 어떻게 수정할지 판단하세요:
  1. L1-b의 접근 자체를 바꾸기 (예: docker 대신 다른 방법)
  2. L2 그래프 구조 변경 (예: 노드 순서 변경, 새 노드 추가)
  3. 이것도 L2에서 해결 불가 → escalate to L3
```

### 7-5. 유저에게 물어볼 때 — 전체 에스컬레이션 체인

L3까지 올라갔는데도 해결 안 되면 `special_action: "ask_user"`. 이때 각 레이어에서 뭘 시도했고 왜 실패했는지를 구조화해서 보여준다:

```
"배포하고 테스트" 작업 중 문제 발생:

[L1] docker build 실패 — 포트 8080 충돌
  └ 시도: 포트 변경(8081) → 여전히 충돌

[L2] 배포 전략 변경 시도 — docker-compose로 전환
  └ 시도: compose 파일 생성 → 네트워크 설정 오류

[L3] 전체 접근법 재검토 — 로컬 직접 실행으로 전환
  └ 시도: venv 생성 → 의존성 충돌

선택지:
  1. 수동으로 포트 문제 해결 후 재시도
  2. 다른 환경(staging 서버 등)에서 실행
  3. 작업 취소
```

### 7-6. 에스컬레이션 후 케이스 저장

에스컬레이션이 발생하면 **원래 케이스를 실패로 mark**하고, 수정된 케이스를 **새 케이스로 저장**한다. 이때 둘 사이의 계보를 추적한다.

#### CaseMetadata 확장 필드

```python
@dataclass
class CaseMetadata:
    # ... 기존 v2 필드 ...

    # === v2.1: 에스컬레이션 계보 ===
    derived_from: str = ""                # 어떤 실패 케이스에서 개선된 건지
    escalation_history: List[dict] = field(default_factory=list)
    # [
    #   {
    #     "from_layer": "L1",
    #     "to_layer": "L2",
    #     "reason": "docker build 포트 충돌 — L1 replan 2회 실패",
    #     "failed_node": "L1-b",
    #     "replan_attempts": 2,
    #   }
    # ]
```

#### 저장 흐름

```
에스컬레이션 발생 → L2 replan 성공:

1. 원래 L2 케이스 (case_id: "def") 업데이트:
   success: false
   error_reason: "L1 docker build 실패 → L2 replan 시도했으나 네트워크 오류"
   escalation_history: [
     {from_layer: "L1", to_layer: "L2", reason: "포트 충돌", ...}
   ]
   # 원래 graph은 그대로 보존 — 다음에 warning으로 활용

2. 새 L2 케이스 (case_id: "xyz") 생성:
   success: true
   satisfaction: 0.85
   derived_from: "def"     ← 이 실패에서 파생됨
   escalation_history: [
     {from_layer: "L1", to_layer: "L2", reason: "포트 충돌",
      resolution: "docker-compose → 직접 실행으로 전환"}
   ]
```

#### 검색 시 활용

```
chaeshin_retrieve(query="서비스 배포해줘")

→ successes:
    - "xyz" (직접 실행 방식, satisfaction 0.85)
      └ derived_from: "def" (docker 방식, 실패)

→ warnings:
    - "def" (docker 방식, 실패)
      └ error_reason: "포트 충돌 → L2 replan 실패"
      └ escalation_history: [{from: L1, to: L2, ...}]

→ LLM/유저 판단: "docker 방식은 전에 포트 충돌로 실패했으니, 직접 실행으로 가자"
```

---

## 8. 구현 우선순위

### Phase 1: 기존 v2 기능 (구현 완료)

| 순서 | 작업 | 상태 |
|---|---|---|
| 1 | `schema.py` — CaseMetadata v2 필드 추가 | ✅ |
| 2 | `case_store.py` — parent/children 연쇄 로드, feedback | ✅ |
| 3 | `mcp_server.py` — retain/retrieve 파라미터 확장 | ✅ |
| 4 | `mcp_server.py` — `chaeshin_feedback`, `chaeshin_decompose` | ✅ |
| 5 | `planner.py` — 계층적 분해(create_tree), apply_feedback | ✅ |
| 6 | `graph_executor.py` — 레이어별 실행(execute_layered) + 체크포인트 | ✅ |
| 7 | `agents/` — Orchestrator, Decomposer, Executor, Reflection | ✅ |

### Phase 2: 자동 에스컬레이션 (v2.1)

| 순서 | 작업 | 설명 |
|---|---|---|
| 1 | `schema.py` — `EscalationPayload`, `CaseMetadata`에 `derived_from`/`escalation_history` 추가 | 에스컬레이션 데이터 구조 |
| 2 | `graph_executor.py` — L1 replan 실패 시 에스컬레이션 판단 로직 | LLM에 "escalate vs fix" 판단 요청 |
| 3 | `graph_executor.py` — `execute_layered`에서 에스컬레이션 수신 처리 | 하위 레이어 실패 로그를 받아 상위 replan 트리거 |
| 4 | `planner.py` — 에스컬레이션 전용 replan 프롬프트 | 하위 로그 전체 + 상위 그래프 컨텍스트 포함 |
| 5 | `case_store.py` — 에스컬레이션 후 저장 로직 | 원래 케이스 실패 mark + 새 케이스 derived_from 연결 |
| 6 | `mcp_server.py` — retain/retrieve에 derived_from, escalation_history 반영 | MCP 인터페이스 확장 |
| 7 | L3 실패 시 ask_user — 전체 에스컬레이션 체인 구조화 출력 | 유저 판단용 정보 포맷 |
