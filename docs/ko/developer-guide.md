# Chaeshin 개발자 가이드 — 문서와 구현을 함께 읽는 법

> 검토 기준일: 2026-08-26
>
> 문서 범위: Docmost `chaeshin` 트리 전체 15페이지(본문 13, 빈 목차 2)
>
> 코드 범위: `chaeshin`, `gsx2-chain`, `bt-agent-monitoring`, `bt-agent-hospital`, `infra`

이 문서는 기존 위키를 축약한 요약본이 아니다. 기존 13개 본문에 흩어진 개념,
데이터 정의, 실행 예시, 운영 절차, 설계안을 개발자가 구현 순서대로 읽을 수 있게
재배치하고, 2026-08-26 현재 코드와 다른 설명에는 상태를 표시한 통합 가이드다.

키오·Survey에서 이 개념을 실제 제품 질문에 대입한 구현·검증 카탈로그는
[키오·Survey × Chaeshin 미래 질문 300선](/bananatouch/chaeshin/docs/ko/kio-survey-chaeshin-300-scenarios.md:1)을
함께 본다. 300개 질문마다 지식 RAG, 환자·운영 데이터, Chaeshin 절차 기억, safety/HITL의
경계를 나누고 현재 readiness와 E2E 합격 기준을 적었다.

## 먼저 알아야 할 결론

Chaeshin은 하나의 동일한 런타임이 아니다. 현재 최소 세 경로가 서로 다른 저장소와
계약으로 동작한다.

1. **로컬/레퍼런스 경로** — stdio MCP + `CaseStore` + SQLite. `pending` 우선,
   계층, revision 기능이 가장 충실하다.
2. **GSX2 운영 경로** — 에이전트 이미지 안의 Chaeshin 라이브러리 + direct Weaviate
   + bt-monitoring 보고. 실행 결과를 즉시 success/failure로 저장하며 로컬 MCP의
   기능 전체를 제공하지 않는다.
3. **AI Hospital 경로** — 자체 PostgreSQL `Case`가 정본이고, Memory MCP 또는
   bt-monitoring REST로 검색 인덱스를 동기화한다. 검색은 Weaviate 직접 read 후
   Hospital DB와 다시 결합한다.

따라서 “Chaeshin은 이렇게 동작한다”는 한 문장 대신, 이 문서에서는 항상 어느
경로를 말하는지 표시한다.

### 상태 라벨

| 라벨 | 의미 |
|---|---|
| **개념** | Chaeshin이 지향하는 공통 불변식과 용어 |
| **현재·로컬** | `chaeshin` 코어와 Claude Code MCP에 실제 구현됨 |
| **현재·운영** | 현재 GSX2/Weaviate/bt-monitoring 배포 경로에 실제 구현됨 |
| **현재·Hospital** | AI Hospital 코드에 실제 구현됨 |
| **목표** | 위키의 채택 설계 또는 향후 운영 모델이며 아직 완성되지 않음 |
| **격차** | 문서와 코드, 또는 런타임 경로 사이의 불일치 |

코드 확인 시점의 주요 revision은 다음과 같다.

| 저장소 | 확인 commit |
|---|---|
| `chaeshin` | `bed0733` (2026-08-04) |
| `gsx2-chain` | `f4556c7` (2026-08-25) |
| `bt-agent-monitoring` | `68cafe9` (2026-08-22) |
| `bt-agent-hospital` | `489365e` (2026-07-08) |
| `infra` | `6b5e590` (2026-08-25) |

### 읽는 순서

- 처음 이해하기: 1 → 2 → 3 → 4장
- 코어/MCP 구현하기: 5 → 6 → 7 → 8 → 9 → 10 → 15장
- GSX2/운영 연동하기: 11 → 12 → 13 → 14 → 16 → 17 → 18장
- 연구 배경과 문서 개편 확인하기: 19 → 20 → 21 → 22장
- 제품 적용과 acceptance test 설계하기: 동반 300선의 1~6장 → 관심 시나리오 → 8장

---

## 1. Chaeshin이 해결하는 문제

### 1.1 RAG가 아니라 절차 기억이다

RAG가 “이 질문에 어떤 지식이 필요한가”를 찾는다면, Chaeshin은 “비슷한 문제를
풀 때 어떤 도구를 어떤 순서와 조건으로 호출했는가”를 찾는다.

기존 에이전트 메모리가 놓치는 문제는 네 가지다.

1. 비슷한 요청이 와도 ReAct 에이전트가 매번 절차를 처음부터 계획한다.
2. 자연어로 저장한 절차는 구조적 diff, 부분 수정, 재현이 어렵다.
3. 하나의 압축 레벨에 고정된 기억은 구체성과 재사용성을 오가기 어렵다.
4. 수정 이력, 되돌리기, 리뷰, 다른 에이전트로의 배포 모델이 약하다.

Chaeshin은 절차를 자연어 단락이 아니라 `ToolGraph`로 저장하고, Case-Based
Reasoning의 4R 사이클을 적용한다.

```text
Retrieve  비슷한 과거 Case를 찾는다
   ↓
Reuse     그래프를 명령이 아닌 참고 힌트로 재사용한다
   ↓
Revise    현재 조건과 피드백에 맞게 수정한다
   ↓
Retain    실제 실행 절차와 결과를 새 Case로 남긴다
```

검색된 그래프는 강제가 아니다. 현재 사용자 입력, 최신 tool schema, 안전 정책,
금기 사항, 의료진/HITL 판단이 언제나 과거 그래프보다 우선한다.

### 1.2 Case의 최소 정신 모델

```text
Case
= ProblemFeatures       무엇을 해결했는가
+ Solution(ToolGraph)   어떤 절차로 해결했는가
+ Outcome               결과와 사후 판정은 어땠는가
+ CaseMetadata          계층·이력·대기·감사 정보
```

이 구조의 정본은 [schema.py](/bananatouch/chaeshin/chaeshin/schema.py:158)다.

### 1.3 일화 기억과 절차 기억

일화(episodic) 기억은 “그 실행에서 무슨 일이 있었는가”를 보존한다. 원문 대화,
tool trace, 관찰, 모델, latency, 오류가 여기에 가깝다. 절차(procedural) 기억은 여러
실행에서 다시 쓸 수 있는 “어떻게 할 것인가”를 ToolGraph로 정리한 것이다.

```text
raw execution / Experience / EventLog
       │ 패턴 추출·검수
       ▼
procedural Case / ToolGraph
```

Episode는 procedure의 근거가 될 수 있지만 둘은 같은 레코드가 아니다. 원본 trace와
모델/비용은 monitoring에 남기고, 재사용할 최소 절차만 Case로 승격하는 것이 좋다.

위키가 인용한 *Experience Compression Spectrum*의 관점에서는 기존 기억 시스템을
대략 세 압축 수준으로 볼 수 있다.

| 수준 | 저장 방식 | 장점 | 한계 |
|---|---|---|---|
| L1 | 개별 경험을 구체적으로 저장 | 원상 재현과 검색이 쉬움 | 양이 빠르게 증가 |
| L2 | 반복 패턴으로 압축 | 재사용이 쉬움 | 구체적 맥락 손실 |
| L3 | 일반 규칙으로 추상화 | 작고 범용적 | 예외 상황에 약함 |

여기서 L1~L3는 논문의 **압축 수준**이며, 7장의 Chaeshin **procedure layer**와 이름만
같고 동일한 schema가 아니다. Chaeshin의 목표는 한 압축 수준에 고정하지 않고,
구체적인 leaf Case와 상위 procedure Case를 관계로 함께 보존하는 것이다.

### 1.4 4R 예시

“60분 안에 불고기와 된장찌개를 함께 준비해 줘”라는 요청을 생각해 보자.

1. Retrieve: 비슷한 한상차림 Case와 실패 warning을 찾는다.
2. Reuse: `재료 확인 → 병렬 손질 → 조리 → 간 확인 → 서빙` graph를 참고한다.
3. Revise: 현재 재료, 알레르기, 인원, 시간 제약에 맞게 node/edge를 바꾼다.
4. Retain: 실제로 실행한 graph와 결과를 저장한다. 로컬 MCP라면 pending으로 시작해
   사용자의 판정을 기다린다.

---

## 2. 실제 시스템 구조

### 2.1 로컬/레퍼런스 경로

```text
Claude Code
    │ stdio MCP
    ▼
chaeshin-mcp (FastMCP)
    │
    ├─ CaseStore
    │    ├─ lexical search
    │    └─ OpenAI embedding (OPENAI_API_KEY가 있을 때)
    │
    └─ SQLite ~/.chaeshin/chaeshin.db
         ├─ cases
         ├─ case_embeddings
         ├─ events
         └─ hierarchy_edges

chaeshin-monitor ── 같은 SQLite를 직접 읽고 씀
```

- MCP는 HTTP 서버가 아니라 stdio `FastMCP`다.
- 기본 DB는 `~/.chaeshin/chaeshin.db`다.
- `CHAESHIN_STORE_DIR`로 프로젝트별 DB 위치를 바꿀 수 있다.
- `OPENAI_API_KEY`가 없으면 lexical 검색으로 동작한다.
- 로컬 `chaeshin-monitor`는 별도 Next.js 앱이며 운영 bt-monitoring UI와 다른
  제품이다.

근거: [mcp_server.py](/bananatouch/chaeshin/chaeshin/integrations/claude_code/mcp_server.py:59),
[sqlite_backend.py](/bananatouch/chaeshin/chaeshin/storage/sqlite_backend.py:42).

### 2.2 GSX2 운영 경로

```text
AG-UI 앱
   │
   ▼
ExpertAgentEngine
   │
   ├─ chaeshin_hint ──> ChaeshinAdapter ──> WeaviateCaseStore ──> Weaviate
   │
   ├─ build_prompt ──> LLM ↔ tools
   │
   └─ retain ─────────> ChaeshinAdapter
                         ├─ direct Weaviate retain
                         └─ bt-monitoring SDK report
                              └─ API → PostgreSQL / Weaviate
```

- 독립 `chaeshin` Deployment나 Service는 현재 없다.
- Chaeshin 소스는 Docker named build context로 GSX2 에이전트 이미지에 포함된다.
- `infra` dev overlay는 `CHAESHIN_WEAVIATE_COLLECTION=ProcChaeshinCbr`를 쓴다.
  코어 기본값 `Experience`와 다르다.
- `GSX2_CHATBOT_ID`가 있으면 자기 chatbot의 Case와 `legacy` Case만 검색한다.
- direct store와 bt-monitoring report가 함께 실행될 수 있어 같은 실행의 중복 또는
  서로 다른 표현이 생길 수 있다.
- 두 표현은 wire-compatible하지 않다. direct store는 완전한 `ProblemFeatures`,
  `ToolGraph`, `{outcome, metadata}`를 쓰지만 monitoring report는 input에
  `{steps, turns}`, metadata에 `{layer, summary, ...}`, edge에 `from/to`를 쓴다.
  core `WeaviateCaseStore` loader는 report 객체를 Case로 복원하지 못하고 건너뛴다.

근거: [engine.py](/bananatouch/gsx2-chain/libs/gsx2_agent/gsx2_agent/engine.py:222),
[chaeshin_factory.py](/bananatouch/gsx2-chain/libs/gsx2_agent/gsx2_agent/chaeshin_factory.py:121),
[apps kustomization](/bananatouch/infra/k8s/apps/kustomization.yaml:17),
[dev overlay](/bananatouch/infra/k8s/overlays/dev/kustomization.yaml:94).

### 2.3 AI Hospital 경로

```text
POST /api/retain
    │
    ├─ PostgreSQL Case 생성                 ← 의료 도메인 정본
    ├─ L2+이면 Evidence 생성
    └─ syncCaseToWeaviate() (best effort)
          ├─ MEMORY_MCP_URL + MEMORY_MCP_KEY 시 bt-memory-mcp retain_procedural
          └─ 아니면 AGENT_REGISTRY_URL + API key로 /api/experiences

POST /api/retrieve
    │
    ├─ Weaviate Experience hybrid 검색
    ├─ Hospital PostgreSQL에 존재하는 case_id만 결합
    └─ 결과가 없거나 Weaviate 미설정이면 PostgreSQL Jaccard fallback
```

Hospital의 PostgreSQL에는 FHIR, LOINC, SNOMED, 환자 프로필, 임상 지표 같은 의료
원본을 보존한다. Weaviate는 검색 인덱스이고, bt-monitoring은 권한·감사·UI 경로다.
권한 link의 실제 강제는 Memory MCP를 선택했을 때에 한정된다.
이 retrieve API는 명시적으로 호출할 때만 동작하며 현재 Hospital council runner에
자동 주입되지 않는다. dev manifest에서 `MEMORY_MCP_URL`은 보이지만 key 주입은
확인되지 않아 REST fallback이 예상된다. 다만 ExternalSecret이 `creationPolicy=Merge`라
기존 Secret에 key가 남아 있을 가능성은 manifest만으로 배제할 수 없다. URL+key가 있어
MCP 경로를 선택한 뒤 호출이 실패해도 같은 요청을 REST로 재시도하지 않는다.

세션 인증은 하지만 Hospital `Case`에 account/tenant 소유 필드가 없고 retrieve query도
소유권 filter를 하지 않는다. 유효한 한 사용자의 검색이 Hospital 전체 Case를 후보로
볼 수 있으므로 multi-tenant 의료 데이터 경계로는 불충분하다.

근거: [retain route](/bananatouch/bt-agent-hospital/src/app/api/retain/route.ts:57),
[sync helper](/bananatouch/bt-agent-hospital/src/lib/cases/sync-to-weaviate.ts:22),
[Hospital retrieve](/bananatouch/bt-agent-hospital/src/lib/council/retrieve.ts:35).

---

## 3. 데이터 모델

### 3.1 `ProblemFeatures`

| 필드 | 타입 | 의미와 검색 반영 |
|---|---|---|
| `request` | `str` | 사용자 원문. 가장 중요한 검색 입력 |
| `category` | `str` | 문제 범주. Python schema에서는 필수지만 wrapper는 빈 문자열 허용 |
| `keywords` | `list[str]` | 명시적 키워드. 저장용 값을 자동 생성하지 않음 |
| `constraints` | `list[str]` | 제약 조건. 로컬 dense/lexical 입력에 포함 |
| `context` | `dict` | 도메인 컨텍스트. 로컬 검색은 깊이 2까지 scalar와 key를 flatten |

중요한 구분이 있다. 빈 `keywords`를 저장용 키워드로 자동 채우지는 않지만, lexical
비교 시에는 `request` 전체를 tokenization한다. 즉 “키워드 자동 추출 없음”은
“요청문을 검색하지 않음”이라는 뜻이 아니다.

로컬 검색 텍스트는 request/category/keywords/constraints/context를 사용한다.
반면 core Weaviate의 query text는 request/category/keywords만 사용한다. 저장된
`inputJson`에는 constraints/context도 들어가므로 BM25 검색 필드로 간접 반영될 수
있지만, query embedding 자체에는 들어가지 않는다.

근거: [search.py](/bananatouch/chaeshin/chaeshin/search.py:109),
[weaviate.py](/bananatouch/chaeshin/chaeshin/integrations/weaviate.py:405).

### 3.2 `GraphNode`

| 필드 | 타입 | 의미 |
|---|---|---|
| `id` | `str` | 그래프 안에서 안정적인 노드 식별자 |
| `tool` | `str` | 실행할 tool 이름 또는 capability id |
| `params_hint` | `dict` | 재사용 시 참고할 기본 인자 |
| `note` | `str` | 단계의 목적과 사람이 읽을 설명 |
| `input_schema` | `dict[str,str]` | 기대 입력 설명. 현재 executor의 강제 validation은 아님 |
| `output_schema` | `dict[str,str]` | 기대 출력 설명. 현재 executor의 강제 validation은 아님 |

L1 leaf는 원칙적으로 한 번의 tool call로 완결되는 원자 패턴이다. “한 Case에 노드가
하나”와 “L1”은 흔히 일치하지만, 코어의 layer 판정은 노드 수가 아니라 자식 Case의
유무로 계산한다.

운영 GSX2의 `retain_l1()`이라는 이름은 이 원칙을 지키지 않는다. 표준 엔진은 최소
2개 tool call이 있는 전체 trace를 한 Case에 넣고 L1이라고 부른다. 이는 core의
topology 기준으로는 자식 없는 L1이지만 “tool 한 번인 원자 패턴” 정의와 충돌한다.

### 3.3 `GraphEdge`

| 필드 | 타입 | 의미 |
|---|---|---|
| `from_node` | `str` | 출발 node id |
| `to_node` | `str \| None` | 다음 node id. `None`이면 특수 action |
| `condition` | `str \| None` | 분기 조건. 없으면 항상 참 |
| `action` | `str \| None` | `to_node=None`일 때 `ask_user`, `emergency_exit` 등 |
| `priority` | `int` | 같은 출발점의 평가 순서 |
| `note` | `str` | 연결 설명 |

canonical 이름은 `from_node`/`to_node`다. 일부 MCP 예시와 GSX2 trace는
`from`/`to`를 사용한다. `CaseStore._graph_from_parts()`와 MCP 입력 parser는 둘 다
받지만 core Weaviate deserializer는 canonical 이름만 받아 `from/to` 객체를 버린다.
GSX2 monitoring report와 UI에서도 변환 누락으로 edge가 보이지 않을 수 있다.

조건 evaluator가 실제 이해하는 형식은 다음 범위다.

```text
nodeId.output.field == value
nodeId.output.field != value
nodeId.output.field > 10
nodeId.output.field == true
nodeId.output.field == null
```

중첩 경로, 임의 Python/JavaScript 식, 복합 boolean 식은 지원하지 않는다.

**격차:** 위키 설명 일부는 큰 `priority`가 먼저라고 하지만 현재 코드는 오름차순으로
정렬하므로 작은 값이 먼저 평가된다. 첫 번째로 참인 edge 하나만 선택한다.

근거: [schema.py](/bananatouch/chaeshin/chaeshin/schema.py:104),
[graph_executor.py](/bananatouch/chaeshin/chaeshin/graph_executor.py:211).

### 3.4 `ToolGraph`

| 필드 | 기본값 | 의미 |
|---|---:|---|
| `nodes` | `[]` | 실행 단계 |
| `edges` | `[]` | 순서, 조건 분기, 루프 |
| `parallel_groups` | `[]` | 동시에 실행할 수 있는 node id 그룹 |
| `entry_nodes` | `[]` | 명시적 시작점. 비어 있으면 incoming edge 없는 node 자동 탐지 |
| `max_loops` | `3` | 완료된 node로 되돌아갈 수 있는 최대 횟수 |

ToolGraph는 DAG로 제한되지 않는다. 역방향 edge와 루프를 허용한다.

### 3.5 `Outcome`

| 필드 | 의미 |
|---|---|
| `status` | 정본 상태: `pending \| success \| failure` |
| `success` | 레거시 bool. `status`에서 동기화 |
| `result_summary` | 실행 결과 요약 |
| `tools_executed` | 실행한 tool 수 |
| `loops_triggered` | 발생한 loop 수 |
| `total_time_ms` | 총 실행 시간 |
| `user_satisfaction` | 0~1 만족도 |
| `error_reason` | 실패 사유 |
| `verdict_note` | 판정 시 남긴 사용자/검수자 메모 |
| `verdict_at` | 판정 시각 |
| `details` | 도메인 확장 결과 |

`status`가 비어 있으면 `success`와 `error_reason`으로 복구하지만, 생성 시에는
`status`를 명시하는 것이 안전하다.

세 값은 개념 계약이지 Python schema의 enum validation은 아니다. `Outcome`은 비어 있지
않은 임의 문자열을 허용하고 `update_case()`도 그대로 저장한다. MCP verdict와
`set_verdict()`만 success/failure를 검사하므로 retain/update/직접 역직렬화 경계에 별도
validation이 필요하다.

### 3.6 `CaseMetadata`

| 그룹 | 필드 |
|---|---|
| 식별/시간 | `case_id`, `created_at`, `updated_at` |
| 사용 품질 | `used_count`, `avg_satisfaction` |
| 출처 | `source`, `version`, `tags` |
| 계층 | `parent_case_id`, `parent_node_id`, `child_case_ids` |
| 판정 대기 | `wait_mode`, `deadline_at` |
| 학습 신호 | `difficulty`, `feedback_count`, `feedback_log` |
| revision | `previous_case_id`, `revision_index`, `is_head`, `revision_reason`, `root_case_id` |

현재 기본값은 UUIDv4, `source="user_session"`, metadata `version=3`이다. 기존 위키의
UUIDv7, 비어 있는 source, version 1 예시는 현재 코드와 다르다.

#### `tags` 자료형 충돌

현재 `CaseMetadata`에는 `tags`가 두 번 선언되어 있다.

- 앞 선언: `list[str]`
- 뒤 선언: `dict[str, int]` — tag 이름에서 revision index로의 포인터

Python dataclass에서는 뒤 선언이 유효하지만 MCP retain은 list를 넣고,
`chaeshin_tag`는 dict로 가정하며, UI는 다시 `string[]`으로 가정한다. 이는 문서 표현의
차이가 아니라 실제 런타임 오류 가능성이 있는 schema 결함이다.

근거: [schema.py](/bananatouch/chaeshin/chaeshin/schema.py:223),
[retain](/bananatouch/chaeshin/chaeshin/integrations/claude_code/mcp_server.py:390),
[tag](/bananatouch/chaeshin/chaeshin/case_store.py:880).

### 3.7 EventLog, Experience, 도메인 DB의 역할

어떤 데이터를 어디에 넣을지는 다음 규칙으로 정리할 수 있다.

| 데이터 | 저장 위치 |
|---|---|
| 검색할 문제 특성 | `ProblemFeatures` |
| 재사용할 실행 절차 | `ToolGraph` |
| 실행 결과와 사후 판정 | `Outcome` |
| 계층, 대기, revision, 피드백 | `CaseMetadata` |
| MCP 호출 타임라인 | SQLite `events` / EventLog |
| 모델, trace, 비용, 권한, 운영 감사 | bt-monitoring `Experience`, `ExecutionSession`, `ExecutionStep` |
| 환자 원본, FHIR, 장기 follow-up | AI Hospital 같은 도메인 PostgreSQL |

SQLite EventLog는 `ts`, `event_type`, `session_id`, `case_ids`, `payload`를 기록한다.
bt-monitoring Experience의 핵심 필드는 `experienceType`, `chatbotId`, `userQuery`,
`isSuccessful`, `feedback`, `keywords`, input/output/metadata JSON, `sourceLogId`다.
`sourceLogId`에는 Case id처럼 재시도에도 같은 안정적인 상관 키를 사용한다. 다만 현재
구현은 PostgreSQL unique 제약이나 Weaviate upsert를 보장하지 않으므로 end-to-end
멱등 키로 간주하면 안 된다.

운영 추적용 선택 필드는 `importance`, `weaviateId`, `traceId`, `sessionId`,
`promptTokens`, `completionTokens`, `model`, `costUsd`다. 이 정보는 재사용 graph 자체가
아니므로 core `CaseMetadata`보다 monitoring에 둔다.

Hospital 도메인 확장에는 `patientProfile`, `clinicalMetrics`, `fhirBundle`,
`loincCodes`, `snomedCodes`, 장기 `Verdict.metrics`, L2+와 L1 원본을 잇는
`Evidence.weight`가 있다. 검색 인덱스에는 필요한 최소 신호만 보내고 의료 원본은
PostgreSQL에 둔다.

잘못된 배치를 피하기 위한 요약:

| 값 | 넣을 곳 | 피할 곳 |
|---|---|---|
| 사용자 입력 조건 | `ProblemFeatures.context` 또는 도메인 DB | `feedback_log` |
| tool parameter 힌트 | `GraphNode.params_hint` | `keywords` |
| 분기 조건 | `GraphEdge.condition` | `note`만으로 표현 |
| 실행 결과 지표 | `Outcome.details` | `ProblemFeatures.context` |
| 장기 follow-up | 도메인 DB + verdict 요약 | 최초 `request` |
| trace/model/cost | bt-monitoring | core `CaseMetadata` |
| 안정적인 상관 키 | `sourceLogId`와 Case id | 임의 tag |
| FHIR/LOINC/SNOMED 원본 | 도메인 DB | 일반 Weaviate 검색 필드 |

PHI와 민감정보는 최소화하고, 고위험 자동 실행에는 contraindication 검사와 HITL 승인
경로를 남긴다.

---

## 4. 한 턴에서 기억이 행동이 되는 과정

### 4.1 표준 GSX2 엔진: 첫 LLM 호출 전에 자동 검색

현재 `ExpertAgentEngine`의 표준 흐름은 다음과 같다.

```text
START
  → chaeshin_hint
  → build_prompt
  → agent ↔ tools
  → retain
  → END
```

1. `chaeshin_hint` node가 사용자 원문으로 최대 3개 사례를 검색한다.
2. `ChaeshinHint`는 성공 패턴, 실패 warning, anticipated graph를 만든다.
3. prompt builder가 이를 “참고용, 반드시 따를 필요 없음”이라는 지시와 함께 system
   prompt에 넣는다.
4. LLM은 과거 패턴과 현재 관찰을 함께 보고 첫 tool을 선택한다.
5. tool loop가 끝나면 최소 tool step 수를 만족한 trace를 자동 retain한다.

`anticipated_graph`에는 현재 위험한 예외가 있다. adapter가 `retrieve_best()`의 상태를
확인하지 않고 graph를 가져오므로 failure나 pending Case도 추천 graph가 될 수 있고,
prompt builder는 그 tool에 추천 표시까지 붙인다. success/failure bucket 설명만 믿고
anticipated graph를 자동 실행하면 안 된다.

즉 표준 엔진에서는 LLM이 첫 turn에 반드시 `memory_retrieve_similar`를 호출해야 하는
것이 아니다. 검색은 이미 LLM 앞에서 수행된다.

근거: [engine.py](/bananatouch/gsx2-chain/libs/gsx2_agent/gsx2_agent/engine.py:278),
[prompt_builder.py](/bananatouch/gsx2-chain/libs/gsx2_agent/gsx2_agent/prompt_builder.py:73).

### 4.2 명시적 memory tool 경로

Dental과 Medical Council에는 LLM이 직접 선택할 수 있는 memory tool도 있다.

```text
LLM tool_call: memory_retrieve_similar
    → LangChain @tool
    → ChaeshinAdapter.retrieve()
    → Weaviate hybrid search
    → formatter
    → role=tool 메시지
    → 다음 LLM turn
```

여러 상위 Case의 첫 단계가 같은 tool을 가리키면 그 tool이 다음 행동의 강한 prior가
된다. 그래도 검색 결과는 명령이 아니며 현재 관찰에 따라 다른 분기를 선택할 수 있다.

**문서 갱신 필요:** 위키의 한 턴 예시는 치과 tool이 raw JSON을 반환하고 Markdown
formatter는 미구현이라고 설명하지만, 현재 Dental 코드는 UUID와 중첩 JSON을 줄인
prompt-friendly Markdown formatter를 이미 사용하고 untrusted data 경계도 표시한다.

운영 원칙은 여전히 유효하다.

- turn마다 바뀌는 tool 결과는 `role=tool`로 유지한다.
- 동적인 검색 결과를 영구 system prompt에 덧붙이지 않는다.
- single-turn API처럼 tool turn을 만들 수 없을 때만 user content 앞에 제한적으로
  합친다.
- 위키의 top-2 약 380→150 token 및 다른 에이전트의 +12~18% 추정치는 방향성
  추정치이지 Chaeshin production benchmark가 아니다.

근거: [Dental tools](/bananatouch/gsx2-chain/apps/dental_chatbot/dental_chatbot/agui/tools.py:1887).

### 4.3 세션 종료 후 retain

표준 엔진은 기본적으로 2개 이상의 tool call이 있어야 자동 retain한다. trace를
ToolGraph로 변환하고 제한적인 tool-result 휴리스틱으로 success 또는 failure를 바로
저장한다.
L1 보고는 bt-monitoring Experience/ExecutionSession/ExecutionStep 보고도 수행할 수
있다.

이 판정은 최종 assistant 답변이나 실제 사용자 만족을 보지 않는다. 각 ToolMessage의
JSON `ok`를 우선 보고, 없으면 문자열에 `권한 거부` 또는 `에러`가 있는지만 검사한다.
대응 ToolMessage를 못 찾은 step은 성공이고 step이 전혀 없어도 전체 성공이다. 자동
성공 retain의 satisfaction은 실제 평가가 아니라 고정 `0.85`다.

이는 로컬 MCP의 “모든 신규 retain은 pending”과 다르다. 자세한 차이는 6장에서
다룬다.

---

## 5. Retrieve — 검색 구현은 세 종류다

### 5.1 로컬 `CaseStore`

검색 대상은 `is_head=True`인 live revision뿐이다.

```text
embedding 없음: lexical 0.8 + quality 0.2
embedding 있음: dense 0.6 + lexical 0.3 + quality 0.1
```

- lexical 내부 점수는 token 유사도 0.75 + category 0.25다.
- quality는 `user_satisfaction`과 `feedback_count` 중 큰 신호를 사용한다.
- embedding 생성이 실패하면 lexical로 fallback한다.
- 반환은 success, failure warning, pending을 구분한다.

근거: [case_store.py](/bananatouch/chaeshin/chaeshin/case_store.py:106).

### 5.2 GSX2 core `WeaviateCaseStore`

| 항목 | 현재 동작 |
|---|---|
| collection | 인자 → `CHAESHIN_WEAVIATE_COLLECTION` → 기본 `Experience` |
| hybrid alpha | embedding 있음 `0.65`, 없으면 `0.0` BM25 only |
| query fields | `userQuery`, `keywords`, `feedback`, `inputJson` |
| 공용 collection filter | `experienceType == "chaeshin-cbr"` |
| chatbot filter | 자기 `chatbotId` 또는 `legacy` |
| score | distance가 있으면 `1-distance`, 아니면 hybrid score clamp |
| 초기 cache | 최대 1,000개 |

전용 collection(`ProcChaeshinCbr`)에서는 collection 자체가 종류를 나타내므로
`experienceType` property/filter를 사용하지 않는다.

주의할 구현 제약:

- 시작할 때 최대 1,000개만 메모리 cache에 올린다.
- cache가 비면 remote collection에 데이터가 있어도 retrieve가 즉시 빈 결과를 낸다.
- query limit도 cache 길이로 제한된다.
- `connect_to_local`만 사용하고 API key/HTTPS 설정을 받지 않는다.
- `retrieve_with_warnings()`가 bool `success`만 사용해 pending을 failure warning으로
  분류한다.
- direct upsert는 transaction 없는 delete 후 insert다.

임베딩과 cutoff는 호출 경로마다 다르다.

| 경로 | 모델/차원 계약 | 결과 수와 cutoff 기본값 |
|---|---|---|
| 로컬 MCP | `OpenAIAdapter` 기본 `text-embedding-3-small`; 원문 Vector 계약은 1,536차원 | success 3, failure 3, `min_similarity=0.5` |
| bare `CaseStore` | 주입된 `embed_fn`; 없으면 lexical | `similarity_threshold=0.7`은 `retrieve_best`에 사용, warning은 0.5 |
| bare `WeaviateCaseStore` | 주입된 `embed_fn` | store threshold 0.7, warning 0.5 |
| 표준 GSX2 adapter | `GSX2MODEL.get_embedding()`의 현재 설정을 사용하므로 모델/차원을 고정하지 않음 | `min_similarity=0.4`, failure 최대 2 |
| Dental 명시 tool | 위 GSX2 adapter 사용 | `top_k=5` |

따라서 `text-embedding-3-small`/1,536차원은 OSS 기본과 원문 저장 계약이지 모든 운영
배포가 자동으로 지키는 불변값은 아니다. 모델을 바꾸면 기존 self-provided vector와의
차원·의미 호환성을 확인하고 같은 collection을 무검증 혼용하지 않는다. 로컬 MCP는
내부 warning cutoff도 0.5이고 최종 `min_similarity`도 0.5라 두 조건을 모두 통과해야 한다.

근거: [weaviate.py](/bananatouch/chaeshin/chaeshin/integrations/weaviate.py:75).

### 5.3 AI Hospital 검색

Hospital은 공통 store wrapper를 그대로 쓰지 않는다.

1. `Experience` collection을 `experienceType=chaeshin-cbr`로 hybrid 검색한다.
2. alpha 0.65의 Weaviate 결과에 lexical 0.25와 quality 0.1을 다시 섞는다.
3. public API top-K를 내부에서 두 배로 넘기고 검색 함수가 다시 네 배를 요청하므로,
   end-to-end로 `min(8 × 요청 topK, 50)`개를 over-fetch한다.
4. `layer`를 후처리로 선택할 수 있다.
5. `sourceLogId`가 Hospital PostgreSQL Case에 실제 존재하는 결과만 반환한다.
6. 결과가 없으면 최신 PostgreSQL Case 최대 500개를 lexical 0.8 + satisfaction 0.2로
   재랭킹한다.

Hospital의 Weaviate 검색은 `WEAVIATE_URL`과 `OPENAI_API_KEY`가 모두 있어야 켜진다.
키가 없을 때 BM25로 낮아지는 core store와 달리 바로 PostgreSQL fallback으로 간다.
또한 collection 이름을 `Experience`로 하드코딩한다. dev GSX2와 monitoring의
`ProcChaeshinCbr` 설정과 다른 collection을 볼 수 있으므로 실제 데이터 공유 여부를
배포 환경에서 반드시 확인해야 한다.

근거: [Hospital weaviate.ts](/bananatouch/bt-agent-hospital/src/lib/weaviate.ts:389),
[retrieve.ts](/bananatouch/bt-agent-hospital/src/lib/council/retrieve.ts:35).

### 5.4 검색 결과의 세 버킷

개념상 반환은 다음 세 그룹이다.

```text
successes  검증된 재사용 후보
failures   비슷한 상황에서 피할 패턴
pending    아직 판정하지 않은 참고 후보
```

로컬 CaseStore와 MCP는 이 구분을 구현한다. 그러나 core Weaviate wrapper와 현재
bt-monitoring UI/DB는 bool을 중심으로 설계되어 pending과 failure가 합쳐질 수 있다.
정확한 상태가 저장돼 있다면 `metadataJson.outcome.status`를 확인해야 한다.

MCP에는 한 가지 응답 shape 예외도 있다. 세 버킷이 모두 비면 빈 배열들을 반환하지
않고 `message`, `search`, `total_in_store`만 반환한다. 호출자는 두 shape를 모두
처리해야 한다.

---

## 6. Retain, deadline, verdict

### 6.1 의도한 공통 상태 모델

```text
retain
  → pending
      ├─ 명시적 성공 판정 → success
      ├─ 명시적 실패 판정 → failure
      └─ 침묵/모호함       → pending 유지
```

deadline 경과는 자동 실패가 아니다. 검토가 늦었다는 운영 신호일 뿐이다.
`blocking`은 검토 전 후속 학습을 막으려는 정책이다.

### 6.2 현재 로컬 MCP

- `chaeshin_retain`은 항상 `Outcome(status="pending")`을 만든다.
- 기본 `deadline_seconds`는 **7,200초(2시간)**다. 위키의 14일 설명과 다르다.
- deadline이 지나도 상태는 pending으로 남고 `stats.overdue_pending`에 집계된다.
- `chaeshin_verdict`가 success/failure를 기록한다.
- satisfaction은 success verdict일 때 0보다 큰 값만 적용한다.

현재 validation 한계도 있다.

- `wait_mode` 값과 음수 deadline을 검증하지 않는다.
- `blocking`의 후속 retain 차단을 실제로 강제하지 않는다.
- satisfaction의 0~1 범위를 검증하지 않는다.
- `set_verdict` 문서 문자열은 pending 전용이라고 하지만 코드에는 재판정을 막는
  상태 검사가 없다.

근거: [mcp retain](/bananatouch/chaeshin/chaeshin/integrations/claude_code/mcp_server.py:309),
[set_verdict](/bananatouch/chaeshin/chaeshin/case_store.py:933).

### 6.3 현재 GSX2 운영

표준 `ExpertAgentEngine`은 위 ToolMessage 휴리스틱만으로 성공/실패를 추론한다.
`ChaeshinAdapter`의 direct store 경로는 즉시 `retain_if_successful()` 또는
`retain_failure()`를 호출한다. 따라서 운영 hot path는 pending-first가 아니다.

명시적 `memory_retain_pattern`도 `success`와 satisfaction을 받아 raw graph를
저장한다. 이 경로를 “downstream이 무조건 pending으로 강제한다”고 설명한 기존
위키는 현재 구현과 맞지 않는다.

### 6.4 현재 AI Hospital

- `POST /api/retain`은 status를 생략하면 pending으로 생성한다.
- 일반 Case 생성 helper는 기본 28일 deadline을 둔다.
- 1주, 4주, 12주 follow-up window를 계산한다.
- 여러 Verdict를 별도 행으로 보존하고 가장 최근 입력이 Case status의 권위 소스가
  된다.
- verdict 반영 후 전체 Case를 같은 `sourceLogId`로 다시 retain하지만 현재 Weaviate
  경로는 이를 upsert하지 않아 이전 상태 객체와 중복될 수 있다.
- sync payload에서는 pending도 `success = (status == "success")`인 bool false로
  축약되어 monitoring/Weaviate에서 failure와 구분되지 않을 수 있다.

Hospital의 임상 장기평가 모델은 코어 MCP의 2시간 deadline과 다른 도메인 정책이다.

근거: [Hospital schema](/bananatouch/bt-agent-hospital/prisma/schema.prisma:72),
[create helper](/bananatouch/bt-agent-hospital/src/lib/cases/create-with-consultation.ts:51),
[verdict route](/bananatouch/bt-agent-hospital/src/app/api/cases/[id]/verdict/route.ts:25).

### 6.5 실패 Case를 왜 보존하는가

failure는 “재사용할 정답”이 아니라 안티패턴 warning이다. 비슷한 문제에서 실패
그래프와 `error_reason`을 함께 노출하면 같은 실수를 반복하지 않을 수 있다.

운영 원칙은 failure를 함부로 삭제하지 않는 것이다. 다만 코어에는 failure를 지우고
success로 교체하는 legacy `promote_failure()`도 남아 있으므로, 감사 요구가 있는
도메인에서는 이 helper를 기본 정책으로 사용하면 안 된다.

---

## 7. Layered Procedure

### 7.1 각 layer는 별도 Case다

하나의 Case 안에 L1~L4를 중첩 저장하는 것이 아니다. 각 layer는 자기 ToolGraph와
Outcome을 가진 별도 Case이고 관계로 연결된다.

```text
L3 전략 Case
  └─ parent node A ↔ L2 sub-procedure Case
                         └─ parent node B ↔ L1 atomic Case
```

연결 필드는 다음과 같다.

```text
child.metadata.parent_case_id
child.metadata.parent_node_id
parent.metadata.child_case_ids
```

- L1: 자식이 없는 leaf. 일반적으로 tool call 한 번.
- L2: L1들을 묶은 sub-procedure.
- L3: 더 큰 plan 또는 coordinator 전략.
- L4+: 전체 업무 흐름이나 상위 전략. 고정 최대 3단계가 아니다.

코어는 layer/depth를 저장하지 않고 자식 subtree 깊이로 계산한다.

```text
depth(case) = 자식 없음이면 0, 아니면 1 + max(child depth)
layer(case) = L{depth + 1}
```

Weaviate metadata와 AI Hospital Prisma는 조회/UI 편의를 위해 layer를 중복 저장할 수
있다. 이 값은 코어의 derived layer와 달라질 수 있다.

현재 link API는 tree 무결성을 강제하지 않는다. self-link와 cycle, `parent_node_id`가
실제 부모 graph에 있는지, reparent할 때 이전 부모 link를 제거했는지를 검사하지 않는다.
SQLite `INSERT OR IGNORE`도 같은 parent-child 쌍의 node anchor 변경을 갱신하지 않는다.
따라서 외부 입력을 연결하기 전에 이 조건을 검증해야 한다.

### 7.2 분해는 host-driven이다

`chaeshin_decompose`가 LLM을 직접 호출해 tree를 만드는 것이 아니다. 유사 Case,
leaf 규칙, 최대 깊이, retain 순서를 호스트 AI에 돌려준다. 호스트가 다음 순서로
저장한다.

1. 루트 Case를 먼저 retain한다.
2. 한 tool call로 끝나지 않는 각 node를 다시 분해한다.
3. 자식 retain에 `parent_case_id`와 `parent_node_id`를 넣는다.
4. 모든 leaf가 한 tool call로 끝날 때까지 반복한다.

코어 planner의 기본 recursive tree 제한은 최대 깊이 4, root node 최대 5,
child node 최대 7이다. MCP `decompose`의 `max_depth`는 최대 6으로 clamp한다.

### 7.3 현재 운영 한계

`WeaviateCaseStore`에는 parent-child link, recursive load, revise, verdict, version API가
없다. GSX2 adapter는 `layer` 인자를 받지만 direct Case의 `CaseMetadata`에는 저장하지
않고 log/report에만 쓴다. retrieve가 없는 `metadata.layer`를 읽으려다 대부분 L1로
fallback한다. Survey도 `retain_l2()`를 호출하지만 child link가 없어 core topology로는
L1이다. link 실패를 adapter가 삼키는 경로도 있다.

---

## 8. ToolGraph 실행

### 8.1 불변 그래프와 가변 실행 상태

실행 중 ToolGraph 자체는 설계도로 유지하고, `ExecutionContext`만 변경한다.

```text
NodeStatus: PENDING → READY → RUNNING → DONE
                                   └→ FAILED
                     필요 시 SKIPPED
```

`ExecutionContext`에는 session/case id, 현재 node, node별 input/output/error,
loop count, graph version, event history가 있다.

### 8.2 실행 순서

1. 명시된 `entry_nodes`, 또는 incoming edge가 없는 node를 READY로 만든다.
2. 같은 `parallel_groups`에 있는 READY node가 둘 이상이면 `asyncio.gather`로 실행한다.
3. 그 밖의 READY node는 순차 실행한다.
4. `params_hint`와 이전 node output을 합쳐 tool 인자를 만든다.
5. tool별 기본 timeout은 300초다.
6. JSON 문자열 결과는 dict로 parse하고, 실패하면 `{"raw": ...}`로 감싼다.
7. outgoing edge를 priority 오름차순으로 평가하고 첫 일치 경로만 연다.
8. 완료된 node로 돌아가면 loop count를 올리고 `max_loops`를 적용한다.
9. deadlock, 실행 실패, matching edge 부재 시 `on_replan` callback을 시도한다.

join node의 모든 predecessor가 끝났는지는 검사하지 않는다. incoming edge 하나가
통과하면 target을 READY로 만들 수 있어 fan-in graph에서는 예상보다 일찍 실행될 수 있다.

### 8.3 계층 실행

`execute_layered()`는 L1부터 bottom-up으로 처리하고 leaf에서만 실제 tool을 실행한다.
상위 layer는 child 결과 내용을 집계하지 않고 `aggregated=True`와 `children_count` marker만
기록한다. layer마다 checkpoint callback이 `continue`, `modify`, `stop`을 반환할 수
있지만, `modify`는 active `for` loop 안에서 execution order 변수만 재할당해 현재
iterator에 반영되지 않는다.

### 8.4 현재 executor 결함

- node 실패와 matching edge 부재에서 받은 새 graph는 지역 변수에만 대입되어 바깥
  실행 loop로 유지되지 않는다. deadlock 경로만 새 graph를 바깥에 반영한다.
- 미등록 tool은 FAILED로 끝나며 FAILED가 terminal로 간주되어 replan 없이 전체 실행이
  종료될 수 있다.
- priority 의미가 문서 설명과 반대인 부분이 있다.
- fan-in node가 모든 predecessor 완료 전에 READY가 될 수 있다.
- layered checkpoint의 `modify`가 현재 순회 순서를 실질적으로 바꾸지 않는다.

근거: [graph_executor.py](/bananatouch/chaeshin/chaeshin/graph_executor.py:61).

### 8.5 로컬 agent lifecycle

코어에는 executor 외에도 별도의 in-process agent stack이 있다.

```text
OrchestratorAgent
  ├─ easy → GraphPlanner.create_graph → GraphExecutor → pending retain
  └─ hard → DecomposerAgent → TaskTree → ExecutorAgent → pending tree retain
                                           └─ feedback 시 ReflectionAgent
```

`BaseAgent.run()`은 progress/checkpoint/result/error event를 내는 async generator다.
`AgentContext`는 session id, parent agent id, conversation history, shared state, available
tools를 담고, `SubagentManager`는 foreground/background/streaming 실행, message append,
result 조회, cancel을 제공한다.

Orchestrator의 현재 분기는 다음과 같다.

1. 유사 Case top-3 중 score 0.4 이상에서 `difficulty>=2` 또는
   `feedback_count>=3`이면 hard다.
2. 그 신호가 없으면 LLM이 easy/hard를 JSON으로 판정하고 파싱 실패는 hard다.
3. easy는 새 graph를 생성·실행하고 pending Case 하나를 저장한다.
4. hard는 최대 깊이 4의 TaskTree를 만들고 leaf를 실행한 뒤 각 tree Case를 pending으로
   재귀 저장한다.
5. `/feedback`이나 명시 호출은 ReflectionAgent로 보낸다.

이 lifecycle의 문서 주석보다 실제 연결은 약하다.

- easy 사전 난이도 검색 결과는 graph reuse에 쓰지 않는다.
- Decomposer가 유사 Case 목록을 만들지만 새 TaskTree에 병합하지 않고, Orchestrator와
  Executor도 그 목록을 사용하지 않는다.
- checkpoint event는 중간 보고일 뿐 현재 `ExecutorAgent`가 사용자 응답을 기다려
  continue/modify/stop을 적용하지 않는다.
- 서브에이전트 생성 시 부모 `AgentContext`를 넘기지 않아 선언된 context 상속이 표준
  Orchestrator 경로에 연결되지 않았다.
- Reflection handler 일부는 9장에서 설명한 revision API를 우회한다.

별도 `ReActAgent`도 있다. 이 구현은 system prompt로 “먼저 retrieve, 마지막에 retain”을
지시하지만 실행 loop가 순서나 호출 여부를 검사하지 않는다. 모델이 바로 Final Answer를
내면 retrieve/retain 없이 종료할 수 있다. 따라서 로컬 agent stack의 자동 CBR reuse를
강한 런타임 보장으로 보면 안 된다.

근거: [orchestrator.py](/bananatouch/chaeshin/chaeshin/agents/orchestrator.py:49),
[base.py](/bananatouch/chaeshin/chaeshin/agents/base.py:57),
[react_agent.py](/bananatouch/chaeshin/chaeshin/agents/react_agent.py:78).

---

## 9. 피드백과 revise

### 9.1 어떤 Case를 수정할지는 호스트가 고른다

Chaeshin이 자연어 한 줄만 보고 자동으로 L1/L2/L3 target을 정하는 것이 아니다.

```text
retrieve(include_children=True)
  → 호스트 LLM이 피드백과 일치하는 node를 찾음
  → 그 node가 속한 case_id를 target으로 선택
  → 현재 graph와 피드백으로 수정 graph 생성
  → chaeshin_revise(target_case_id, graph, reason)
```

피드백 분류는 다음 다섯 가지다.

| 유형 | 의미 |
|---|---|
| `escalate` | 현재 절차를 더 큰 절차 아래로 이동 |
| `modify` | 순서, node, edge를 일반 수정 |
| `simplify` | 하위 단계를 합치거나 끌어올림 |
| `correct` | 잘못된 tool/parameter를 교체 |
| `reject` | 불필요한 단계 제거 |

`ReflectionAgent`와 planner가 처리하는 유형은 위 다섯 가지다. MCP `feedback`은 여기에
`auto`를 공개하지만 실제 값을 검증하거나 LLM으로 분류하지 않고 그대로 log에 넣는다.

LLM 기반 수정은 별도 `GraphPlanner.apply_feedback()` 경로다. system 입력은 선택된
Case의 현재 graph JSON과 `feedback_type` hint이고, user 입력은 피드백 원문이다. 출력
계약은 다음과 같다.

```json
{
  "type": "escalate|modify|simplify|correct|reject",
  "diff": {
    "added_nodes": [],
    "removed_nodes": [],
    "added_edges": [],
    "removed_edges": [],
    "updated_nodes": []
  },
  "new_subtasks": [],
  "reasoning": "변경 이유"
}
```

JSON 파싱에 실패하면 명시된 유형을 유지하고, `auto`였다면 `modify`와 빈 diff로
fallback한다. 단, 현재 `ReflectionAgent`의 modify/correct/simplify handler는
`revise_graph()`를 통하지 않고 객체를 직접 바꿔 다시 retain하므로 아래 revision
계약을 우회한다.

### 9.2 현재 `revise_graph()` 동작

1. live HEAD만 수정한다.
2. 전후 graph의 node/edge diff를 계산한다.
3. 수정 전 HEAD 전체를 새 UUID, `is_head=False`인 snapshot으로 복사한다.
4. 원래 안정적인 `case_id`의 HEAD graph를 새 graph로 바꾼다.
5. `previous_case_id`, `revision_index`, `revision_reason`을 갱신한다.
6. 제거된 parent node에 연결된 child를 찾는다.
7. `cascade=True`이면 child를 삭제하지 않고 pending으로 되돌리고 review note를 남긴다.
8. added/removed/retained/changed node, edge diff, `orphaned_children`을 반환한다.

`cascade=False`이면 6~7의 child 상태 변경만 건너뛰고 snapshot과 HEAD 수정은 그대로
수행한다. 전파 범위도 아래 방향뿐이다. 대상 layer와 제거된 node에 매달린 직접 child를
보고, 그 Case의 부모나 형제 Case를 수정하지 않는다. 또한 snapshot의 불변성은
`is_head=False` 관례일 뿐 storage write guard가 아니다. `update_case(snapshot_id, ...)`
같은 일반 경로는 snapshot도 바꿀 수 있다.

`update_case()`는 metadata/outcome 같은 얕은 필드 patch용이고, graph 구조는
`revise_graph()`를 사용해야 revision history와 cascade가 남는다.

예를 들어 `Read → Edit → Test`에 “Test 전에 Lint를 넣고 Edit는 빼라”는 피드백이
오면 호스트가 `Read → Lint → Test` graph를 만들어 revise한다. 코어는 Edit 제거,
Lint 추가, edge 교체를 diff로 계산하고, 기존 `Read → Edit → Test` 전체를 snapshot에
남긴다. 계층 graph에서 제거한 node에 child Case가 붙어 있었다면 그 child id가
`orphaned_children`으로 반환된다.

### 9.3 Safe unlink는 목표 설계다

위키가 원하는 최종 모델은 parent graph에서 node가 사라져도 child Case의 성공
Outcome을 바꾸지 않고, 독립된 binding만 `unlinked`로 바꾸는 것이다.

```text
Case.outcome.status        success 유지
CaseBinding.status         linked → unlinked
```

현재 코어는 독립 `CaseBinding`이 없고 orphan child의 Outcome 자체를 pending으로
되돌린다. Review UI의 `binding=unlinked` 필터도 목표 모델이지 현재 공통 운영 계약이
아니다.

### 9.4 변경 의도도 아직 분리되지 않았다

사용자 요청은 다음 네 가지로 나뉘어야 한다.

| 의도 | 처리 |
|---|---|
| run-level override | 이번 실행만 변경, 기억은 수정하지 않음 |
| procedure variant | 조건이 다른 새 Case로 retain |
| procedure correction | 기존 Case graph revise |
| case verdict | success/failure 판정만 변경 |

목표 설계의 `ChangeIntent`, `ProcedureRun`/`ExecutionOverride`, `variant_of`,
`variant_reason`, `trigger_phrases`, `supporting_episode_ids`, `retain_variant()`는 현재
공통 schema/API에 구현되지 않았다.

---

## 10. 버전 관리 — 현재 구현과 목표 모델

### 10.1 현재 구현

로컬 `CaseStore`와 MCP에는 다음이 실제로 있다.

| 기능 | 현재 동작 |
|---|---|
| revise | 수정 전 전체 graph를 snapshot으로 남기고 stable HEAD 갱신 |
| history | HEAD부터 `previous_case_id` chain을 최신순 조회 |
| diff | 두 Case version의 node/edge 구조 차이 |
| revert | 과거 graph를 HEAD에 복사하되 새 revision commit으로 남김 |
| blame | 현재 node가 마지막으로 들어온 revision과 reason 조회 |
| tag | tag 이름 → revision index 포인터 |

현재 revision은 전체 graph snapshot 방식이다. snapshot 저장, HEAD 저장, orphan child
저장이 각각 독립 transaction이므로 revision 전체가 atomic하지 않다. 중간 실패 시
부분 상태가 생길 수 있다.

또한 `ReflectionAgent`와 로컬 monitor의 일부 edit 경로는 `revise_graph()` 대신 객체나
SQLite JSON을 직접 갱신하므로 snapshot/version chain을 우회한다.

### 10.2 위키의 확장 목표

위키의 “10종 원자 연산 + Git형 이력”은 현재 구현 설명이 아니라 확장 설계다.

| 범주 | Op |
|---|---|
| node | `node_add`, `node_rm`, `node_replace` |
| edge | `edge_add`, `edge_rm`, `edge_redirect` |
| hierarchy | `graph_nest`, `graph_unnest`, `graph_merge`, `graph_split` |

피드백 레시피는 다음처럼 정의한다.

- CORRECT → `node_replace`
- REJECT → node/edge 제거 + bypass edge
- MODIFY → before/after structural diff
- ESCALATE → graph nest + 상위 node/edge
- SIMPLIFY → graph merge

각 Op의 inverse, `GraphCommit`, `GraphChangeLog`, 3-way merge revert, 다른 Case의
cherry-pick, 상쇄 연산을 제거하는 squash는 아직 코어에 없다.

목표 알고리즘의 3-way operand는 다음처럼 정의돼 있다.

| 작업 | base | ours | theirs |
|---|---|---|---|
| revert | 되돌릴 commit 적용 직후 | 이후 수정이 반영된 현재 graph | 해당 commit 적용 전 `snapshot_before` |
| cherry-pick | source commit 직전 snapshot | target Case의 현재 graph | source ops 적용 후 graph |

충돌이 없을 때만 merge하고, squash는 연속 commit의 `node_add` 후 `node_rm`처럼 서로
상쇄되는 Op를 제거해 하나의 commit으로 만드는 목표다.

### 10.3 메모리 2축 모델도 목표 거버넌스다

Lifecycle 축:

```text
Trace → Candidate(pending) → Committed(success 검수)
```

Scope 축:

```text
Local → Stage(review) → Hub(shared standard)
```

의도한 전환은 `extract`, 검수·확인, `push`, `merge`, `fork`다. Trace는 Local에만,
Hub에는 Committed만 허용한다. 현재 공통 API와 배포에는 이 2축 promotion workflow가
완성되어 있지 않다.

ToolGraph를 상태-행동-다음 상태의 구조적 기록으로 보는 관점은 MDP와 닿아 있고,
부분 관찰 환경에서는 POMDP의 관찰 기반 action trace에 해당한다. 이것은 이론적
설명이지 현재 executor가 RL policy를 학습한다는 뜻은 아니다.

---

## 11. Tool 변경에 강한 절차 기억

### 11.1 문제

저장된 leaf node가 구체적인 tool 이름과 parameter에 직접 결합되면 rename, 제거,
signature 변경 때 과거 Case가 깨진다. 결합은 주로 실제 tool을 호출하는 leaf에 산다.

| 변경 | literal graph에 미치는 영향 |
|---|---|
| rename | 죽은 tool key로 실행 실패 |
| remove | 구현 없는 node로 실행 실패 |
| parameter signature 변경 | stale `params_hint` 전달 |
| 이름·signature는 같고 의미만 변경 | 구조상 정상처럼 보이는 의미 drift |
| add | 기존 graph는 동작하지만 더 나은 tool을 쓰지 못할 수 있음 |

검토한 선택지는 세 가지다.

| 방식 | 장점 | 한계 |
|---|---|---|
| 현재 literal id | 즉시 executable, 추가 계층 없음 | Case N개에 tool 이름이 박힘 |
| capability registry | executable을 유지하면서 수정 지점을 registry 한 곳으로 모음 | registry 운영·curation 필요 |
| 매번 LLM으로 절차 재생성 | tool 변화에 자동 적응 가능 | 결정성·실행 자산성을 잃고 매번 추론 비용 발생 |

Chaeshin은 두 번째 방식을 채택했다.

### 11.2 채택 설계

결합을 Chaeshin core에 퍼뜨리지 않고 GSX2 agent layer의 capability registry에 모은다.

```text
create/execute 시점     현재 실제 tool 이름 사용
retain 직전             tool → capability_id 역매핑
저장                    capability_id
retrieve/execute 직전   capability_id → 현재 tool + parameter mapping
```

예:

```text
저장: scoring.survey.dynamic
현재 실행: score_survey_v4
목표 param_map: domains → domain_set
```

### 11.3 현재 구현 범위

기존 위키는 capability registry를 미래형으로 설명하지만 현재 GSX2에는
`CapabilityRegistryBridge`가 구현되어 있다.

- bt-monitoring `/api/capabilities/manifest`를 API key로 읽는다.
- TTL 기본 300초로 tool↔capability map을 cache한다.
- retain 전 leaf tool 이름을 capability id로 바꾼다.
- retrieve한 graph의 capability id를 현재 live tool 이름으로 해석한다.
- 매핑되지 않은 이름은 literal tool 이름으로 남긴다.

아직 없는 부분:

- signature 변경을 자동 보정하는 `param_map`
- 해석 불가 Case의 `needs_curation` 상태
- 모든 retain 진입점의 일관된 rewrite. L1 trace 경로는 rewrite하지만 명시적
  `retain_graph()` 경로는 literal 이름이 남을 수 있다.

근거: [capability_registry_bridge.py](/bananatouch/gsx2-chain/libs/gsx2_agent/gsx2_agent/capability_registry_bridge.py:1).

---

## 12. 에이전트 통합

### 12.1 표준 통합점

GSX2에서 새 agent를 붙일 때 표준 통합점은 `ChaeshinAdapter`와 factory다.

```python
adapter = build_chaeshin_adapter(...)

config = EngineConfig(
    auto_retain_chaeshin=True,
    chaeshin_min_tool_steps=2,
)
```

실제 API 이름과 생성자 인자는 앱 버전에 따라 factory를 따라야 하며, 위 코드는 개념
형식이다. 직접 `WeaviateCaseStore`를 중복 생성하기보다 공통 factory로 chatbot cuid,
collection, embedding, monitoring SDK, capability bridge를 한 번에 맞추는 편이 안전하다.

backend 우선순위는 명시 adapter → direct CaseStore → MCP → Chaeshin 없음이다.

### 12.2 현재 확인된 서비스

| 서비스/진입점 | Retrieve | Retain | 명시 tool / monitoring |
|---|---|---|---|
| Dental `/chat/v2/stream` | 첫 LLM 전 자동 | tool 2개 이상이면 자동 L1 | 두 in-process memory `@tool`; Experience/Session/access audit |
| Lifecare 본체 | 첫 LLM 전 자동 | tool 2개 이상이면 자동 L1 | 두 in-process memory `@tool`; Experience/Session/access audit |
| Wiki | 첫 LLM 전 자동 | tool 2개 이상이면 자동 L1 | 명시 memory tool 없음; Experience/Session/access audit |
| Survey `/v2/process-survey` | 고정 graph node | 마지막 node에서 L2 | direct Weaviate, monitoring API mirror 없음 |
| Survey 기본 `/process-survey` | 없음 | 없음 | Chaeshin 미사용 |
| Medical Council | LLM이 memory tool을 골라야 함 | LLM이 L2 retain tool을 호출해야 함 | 두 in-process `@tool`; direct Weaviate만 |
| AI Hospital | `/api/retrieve` 명시 호출만 | `/api/retain`/verdict/follow-up | 서버 API; manifest상 monitoring REST fallback 예상 |
| Health chat | 없음 | 없음 | engine에 adapter가 주입되지 않음 |
| Health professional review | 없음 | 합성 trace만 별도 retain | direct Weaviate만 |
| Consultation | 없음 | 없음 | 미통합·미배포 |
| Result Creator | 없음 | 없음 | 배포되지만 Chaeshin 미통합 |
| Persona Worker | 없음 | 없음 | 향후 교체 주석만 있는 dry-run stub |
| Lifecare extraction worker | 없음 | 없음 | Lifecare 본체와 달리 Chaeshin 미사용 |

운영 자동 통합은 현재 Dental v2, Lifecare 본체, Wiki 세 앱이다. “모든 ReAct
서비스가 Chaeshin을 쓴다”는 주장은 사실이 아니다. 공통 엔진을 사용해도 adapter를
주입하지 않거나 `auto_retain_chaeshin=False`인 앱이 있다.

`memory_retrieve_similar`와 `memory_retain_pattern`은 core Chaeshin MCP 도구가 아니라
각 앱 프로세스 안의 LangChain `@tool`이다. Dental은 환경변수가 맞으면 이 둘과
별도로 generic bt-memory-mcp 도구들도 추가로 등록한다.

자동 trace retain만 bt-monitoring 보고를 수행한다. `retain_graph()`, L2/L3 retain,
Survey/Medical Council/Health review의 direct Weaviate 저장은 API mirror를 만들지 않아
PostgreSQL을 읽는 Monitoring UI에 나타나지 않을 수 있다.

서비스별 확인 지점:

- [Dental graph](/bananatouch/gsx2-chain/apps/dental_chatbot/dental_chatbot/agui/react_graph.py:446),
  [Dental tools](/bananatouch/gsx2-chain/apps/dental_chatbot/dental_chatbot/agui/tools.py:1887)
- [Lifecare graph](/bananatouch/gsx2-chain/apps/lifecare_agent/lifecare_agent/agui/react_graph.py:329),
  [Lifecare tools](/bananatouch/gsx2-chain/apps/lifecare_agent/lifecare_agent/agui/tools.py:2725)
- [Wiki graph](/bananatouch/gsx2-chain/apps/wiki_agent/wiki_agent/agui/react_graph.py:101)
- [Survey v2 graph](/bananatouch/gsx2-chain/apps/survey_agent/survey_agent/graph_v2.py:94)
- [Medical Council factory](/bananatouch/gsx2-chain/apps/medical_council_agent/medical_council_agent/factory.py:57),
  [memory tools](/bananatouch/gsx2-chain/apps/medical_council_agent/medical_council_agent/tools/memory.py:24)
- [Health chat](/bananatouch/gsx2-chain/apps/health_agent/health_agent/routes/agent_chat_v2.py:57),
  [professional review](/bananatouch/gsx2-chain/apps/health_agent/health_agent/routes/professional_reviews.py:148)

### 12.3 adapter의 현재 주의점

- retrieve 예외를 삼키고 빈 hint로 반환하므로 장애가 “기억 없음”처럼 보인다.
- chatbot slug를 bt-monitoring cuid로 해석해 cache한다. 최초 lookup 실패도 프로세스
  동안 slug로 cache될 수 있어 cuid-scoped Case를 못 볼 수 있다.
- `_WeaviateStoreCompat`가 pending을 보존하지 않는다.
- monitoring report의 input/metadata/edge shape는 core direct serializer와 달라 core
  `WeaviateCaseStore`가 그 객체를 Case로 읽지 못한다.
- canonical edge `from_node`/`to_node`를 받는 일부 retain 경로에서 adapter가
  `from`/`to`만 읽어 빈 endpoint를 만들 수 있다.
- MCP fallback retain은 현재 MCP signature에 없는 `satisfaction`, `success`,
  `error_reason`을 보낸다.
- MCP-only anticipate는 코어에 없는 `chaeshin_anticipate`를 호출한다.
- Health의 `/api/agent/review` 계열 한 경로는 async `service.retain()`에 `await`가
  빠져 있어 professional-review의 정상 별도 경로와 달리 저장 완료를 보장하지 못한다.

따라서 새 서비스는 “direct Weaviate에서 동작함”만 확인하지 말고 MCP fallback,
monitoring mirror, edge rendering까지 각각 검증해야 한다.

---

## 13. 저장소와 Vector DB 계약

### 13.1 3-tier 역할

| 저장소 | 역할 | 정본 여부 |
|---|---|---|
| SQLite | 개발자 로컬 Case/MCP/EventLog | 로컬 경로의 정본 |
| Weaviate | 공유 hybrid retrieval index | 운영 검색 인덱스 |
| bt-monitoring PostgreSQL | Experience UI, 권한, 감사 | 운영 UI/감사 mirror |
| Hospital PostgreSQL | 의료 Case와 장기 평가 | Hospital 도메인의 정본 |

### 13.2 Weaviate property 매핑

| Weaviate | Chaeshin |
|---|---|
| `experienceType` | `chaeshin-cbr` |
| `chatbotId` | 소유/검색 scope |
| `userQuery` | `problem_features.request` |
| `isSuccessful` | legacy `outcome.success` |
| `feedback` | 주로 `outcome.error_reason` |
| `keywords` | `problem_features.keywords` |
| `inputJson` | 전체 `ProblemFeatures` |
| `outputJson` | `ToolGraph` |
| `metadataJson` | `{ outcome, metadata }` |
| `sourceLogId` | 안정적인 Case 상관 키; 의도는 upsert지만 현재 전 계층 멱등 보장 없음 |
| `postgresId` | 의도상 PostgreSQL mirror id; core direct와 monitoring POST에서는 빈 값 |
| `createdAt` | 생성 시각 |

전용 collection에서는 `experienceType` property가 없을 수 있다. collection schema는
Chaeshin core 또는 bt-monitoring 중 누가 먼저 생성했는지에 따라 조금 달라질 수 있고,
이미 존재할 때 schema reconciliation을 하지 않는다.

이 표는 core direct serializer의 canonical mapping이다. GSX2의 bt-monitoring report는
같은 property 이름 안에 다른 JSON shape를 넣어 core loader와 호환되지 않는다.

### 13.3 SQLite schema와 migration

SQLite 테이블은 다음 네 개다.

- `cases`: 전체 JSON + parent/category/success 등의 검색 mirror column
- `case_embeddings`: case id별 vector JSON
- `events`: MCP event timeline
- `hierarchy_edges`: parent/child join 편의를 위한 중복 관계

startup은 `CREATE TABLE IF NOT EXISTS`만 수행한다. 다음 migration은 자동 runner 없이
수동 모듈로 존재한다.

- m001: legacy JSON → SQLite
- m002: outcome status backfill
- m003: stored layer/depth 제거

version table과 startup migration이 없으므로 배포 업그레이드 순서를 운영자가 관리해야
한다. `cases.success` mirror는 bool이라 pending과 failure를 구분하지 못하며 정확한
상태는 `outcome_json.status`에만 있다.

### 13.4 계층 read 비용과 closure table 기준

현재 adjacency-list 모델에서 runtime 유사도 검색은 계층을 펼치지 않으므로 hot path가
한 번의 Weaviate query로 끝난다. 비용이 커지는 곳은 review/monitoring의 cold path다.

| read | 현재 복잡도 |
|---|---|
| runtime retrieve | 1 query |
| leaf에서 root까지 ancestor | core list scan 때문에 O(depth × N) |
| root의 전체 subtree | 최악 O(N²)에 가까움 |
| core `derive_layer` | 최악 O(N²)에 가까운 subtree walk |
| Hospital의 저장된 layer 조회 | 1 read, 대신 stale 가능성 |

여기서 N은 로컬 `CaseStore.cases` 전체 길이다. `get_case_by_id()`와 child 조회가 index가
아닌 list scan이어서 단순 adjacency-list 이론치보다 실제 코어 비용이 크다.

위키는 closure table 도입 신호를 subtree fetch p95 200ms 초과, review session당 평균
read 50회 초과, Hospital Case 10k 초과로 제안한다. 이 수치는 현재 SLO나 구현된 자동
전환이 아니라 premature optimization을 피하기 위한 설계 기준이다.

### 13.5 선택적 로컬 store와 교환 adapter

| 구성요소 | 현재 계약 | 주의점 |
|---|---|---|
| `ChromaCaseStore` | 기본 collection `chaeshin_cases`, cosine, `persist_dir`가 있으면 PersistentClient 아니면 ephemeral, threshold 0.7 | Case JSON을 metadata에 40,000자로 자름. 재시작 시 기존 collection을 `cases` cache로 hydrate하지 않아 query hit를 Case로 복원하지 못함 |
| `OpenAIAdapter` | chat 기본 `gpt-6-luna`(reasoning_effort `none`), embedding 기본 `text-embedding-3-small`, temperature 0.2, max completion tokens 4,096 | chat은 async, embedding은 sync. 호출자가 모델/키를 주입하며 MCP는 key가 없으면 lexical |
| `ChaebiClient` | Bearer REST로 approved Case pull, learned Case push, id/category/status export | pull `/api/chaeshin/sync` 기본 limit 50, push도 같은 endpoint, export는 `/api/chaeshin/export`; 원격 검증/권한은 Chaebi 서버 책임 |

Chaebi 변환은 node/edge/top-level graph 필드를 비교적 완전하게 옮기지만 현재
`CaseMetadata.tags` 자료형 충돌은 그대로 공유한다. 이 세 adapter는 표준 GSX2 운영
경로가 아니라 선택적 OSS/local 기능이다.

근거: [chroma.py](/bananatouch/chaeshin/chaeshin/integrations/chroma.py:48),
[openai.py](/bananatouch/chaeshin/chaeshin/integrations/openai.py:27),
[chaebi.py](/bananatouch/chaeshin/chaeshin/integrations/chaebi.py:30).

---

## 14. Monitoring UI와 권한

### 14.1 두 UI를 구분한다

| UI | 데이터 | 배포 상태 |
|---|---|---|
| `chaeshin-monitor` | 로컬 SQLite 직접 접근 | K8s 미배포, 개발용 |
| `bt-agent-monitoring` | PostgreSQL Experience + ExperienceType별 Weaviate | 운영 UI |

로컬 monitor의 PUT/revise 일부는 Python version chain을 우회한다. 인증 없는 CRUD API도
있으므로 외부에 그대로 배포하면 안 된다.

두 UI가 같은 SQLite를 자동으로 찾는 것도 아니다. MCP는 `CHAESHIN_STORE_DIR` 아래의
`chaeshin.db`를 읽고, monitor는 `CHAESHIN_DB_PATH`를 읽는다. 프로젝트별 MCP 저장소를
쓸 때는 예를 들어 다음처럼 두 값을 같은 파일로 맞춰야 한다.

```bash
export CHAESHIN_STORE_DIR=/absolute/path/to/project/.chaeshin
export CHAESHIN_DB_PATH=/absolute/path/to/project/.chaeshin/chaeshin.db
```

### 14.2 운영 화면

위키가 설명하는 주요 화면은 다음과 같다.

- `/memory/procedural` — procedural store 목록
- `/memory/procedural/[storeName]` — Chaeshin Case 목록/상세
- `/experience-types` — `chaeshin-cbr` type 및 storage 설정
- `/memory-access` — chatbot별 recall/retain/delete/admin 권한
- `/memory/stores` — 물리 store와 schema 상태

Case를 검토할 때 순서는 다음이 안전하다.

1. request와 category가 검색 의도를 표현하는지
2. node가 실제 실행 가능한 tool/capability 단위인지
3. edge condition이 현재 evaluator가 이해하는 문법인지
4. `sourceLogId`가 안정적이고 중복되지 않는지
5. bool `isSuccessful`만 보지 말고 `metadata.outcome.status`가 무엇인지
6. UI 변경이 PostgreSQL뿐 아니라 retrieval Weaviate에도 반영됐는지

### 14.3 수동 Case 생성, 편집, verdict

외부 curl은 `x-api-key` 인증을 사용한다. 실제 `requireApiKey`는 서명된 운영자 session
cookie도 허용한다. 새 Case는 안정적인 `sourceLogId`를 정하고, bool 필드와 3-state
metadata를 함께 넣는다.

```bash
curl -X POST http://localhost:3001/api/experiences \
  -H 'content-type: application/json' \
  -H 'x-api-key: <MONITORING_ADMIN_API_KEY>' \
  -d '{
    "experienceType": "chaeshin-cbr",
    "chatbotSlug": "ai-hospital",
    "sourceLogId": "manual-diabetes-intake-001",
    "userQuery": "야간 근무 T2DM 신환 관리 계획",
    "isSuccessful": false,
    "keywords": ["T2DM", "야간근무"],
    "input": {
      "request": "야간 근무 T2DM 신환 관리 계획",
      "category": "diabetes-intake",
      "keywords": ["T2DM", "야간근무"],
      "constraints": [],
      "context": {}
    },
    "output": {
      "nodes": [
        {"id": "intake", "tool": "lifestyle_intake", "note": "생활습관 문진"},
        {"id": "risk", "tool": "risk_stratify", "note": "위험도 분류"}
      ],
      "edges": [{"from_node": "intake", "to_node": "risk"}],
      "parallel_groups": [],
      "entry_nodes": ["intake"],
      "max_loops": 3
    },
    "metadata": {
      "outcome": {"status": "pending", "success": false, "user_satisfaction": 0},
      "metadata": {
        "case_id": "manual-diabetes-intake-001",
        "source": "clinical_protocol",
        "tags": ["T2DM", "야간근무"]
      }
    }
  }'
```

POST는 같은 `experienceType` + `sourceLogId`를 `findFirst`로 찾아 PostgreSQL row를
갱신하려고 한다. 그러나 DB unique 제약이 없고 조회에 `chatbotId`도 없어서 동시 요청은
중복되고 다른 chatbot끼리 충돌할 수 있다. Weaviate에는 호출마다 새 UUID로 insert되어
이 키로 upsert되지 않는다. `sourceLogId`를 생략하면 재시도와 원본 추적은 더
어려워지지만, 넣는 것만으로 전체 저장 경로의 멱등성이 생기지는 않는다.

dual-write도 atomic하지 않다. route는 Weaviate/Mongo/Neo4j 같은 외부 backend를 먼저
쓴 뒤 PostgreSQL을 create/update하며 transaction, outbox, 보상 삭제가 없다. PostgreSQL
실패 시 외부 고아 객체가 남고, 외부 store가 미설정·연결 실패로 id를 돌려주지 않아도
PostgreSQL-only row는 만들어질 수 있다.

POST는 `userQuery`, `feedback`, `input`, `output`, `metadata`에 PII masking을 적용하지만
`keywords`는 제외한다. guardrail 기본값은 shadow이고 평가 실패 시 fail-open이다.
masking 자체도 `GUARDRAIL_MASK_DISABLE`로 끌 수 있다. PUT과 backfill에는 같은
masking/guardrail이 없다.

상세 화면에서 graph나 metadata를 저장하는 실제 API는
`PUT /api/experiences/{id}`다. 성공 판정 예시는 다음과 같다.

```bash
curl -X PUT http://localhost:3001/api/experiences/<POSTGRES_EXPERIENCE_ID> \
  -H 'content-type: application/json' \
  -H 'x-api-key: <MONITORING_ADMIN_API_KEY>' \
  -d '{
    "isSuccessful": true,
    "feedback": "2주 후 증상 소실, 환자 만족",
    "metadata": {
      "outcome": {
        "status": "success",
        "success": true,
        "verdict_note": "2주 후 증상 소실, 환자 만족",
        "user_satisfaction": 0.9
      },
      "metadata": {
        "case_id": "manual-diabetes-intake-001",
        "source": "clinical_protocol",
        "tags": ["T2DM", "야간근무"]
      }
    }
  }'
```

실패 판정은 `isSuccessful=false`, `outcome.status="failure"`, `error_reason`을 함께
보낸다. PUT은 포함된 top-level 필드만 patch하지만 `input`, `output`, `metadata` JSON은
각각 통째로 교체하므로 보존할 하위 필드를 모두 보내야 한다. 문구나 node note를
바꾸는 운영 편집에는 쓸 수 있지만, 같은 row를 덮어써 revision chain을 남기지 않는다.
구조 변경에 이력이 필요하면 core `chaeshin_revise` 경로를 사용하거나 그 기능을 운영
API에 연결해야 한다.

삭제 전에는 원본 서비스가 같은 `sourceLogId`로 다시 sync해 Case를 되살리는지 확인한다.
현재 PUT은 `updateExperience()`에 필수 `experienceType`을 전달하지 않아 Weaviate
동기화가 항상 `false`로 끝나며, route는 이를 오류로 처리하지 않는다. UI가 보낸
`userQuery`도 route가 읽지 않는다. 따라서 성공 응답/toast가 보여도 PostgreSQL만
바뀌고 retrieval index는 그대로다. Hospital verdict 재동기화 역시 Weaviate에 과거
pending/failure 객체를 남길 수 있고, DELETE는 PostgreSQL row가 기억하는 외부 ID 하나만
지운다. 이 상태에서는 코드 수정과 중복 정리 전까지 UI verdict/edit를 retrieval 반영
수단으로 신뢰하면 안 된다.

### 14.4 ExperienceType와 권한

개념상 기본 등록은 다음과 같다.

```yaml
name: chaeshin-cbr
displayName: Chaeshin CBR
kind: procedural
template: chaeshin
storeKind: weaviate
storeClass: Experience       # legacy 표시 필드
weaviateClassName: ProcChaeshinCbr  # 실제 collection; 서버가 부여
```

`/memory-access`의 `ChatbotExperienceTypeLink`는 `recall`, `retain`, `delete`, `admin`
정책을 저장한다. 실제 강제 지점은 Memory MCP 경로다. Monitoring REST POST/PUT과 direct
Weaviate는 이 link를 검사하지 않고, REST DELETE도 `x-mcp-chatbot-id`가 있을 때만
delete/admin 및 row 소유권을 검사한다. AI Hospital이 URL+key로
`retain_procedural`을 쓸 때만 이 권한층을 통과하며 REST fallback은 API key 인증만 한다.

선택적으로 도메인별 type을 별도 collection에 둘 수도 있다.

```yaml
name: chaeshin-ortho-cbr
displayName: 교정 절차 기억
kind: procedural
template: chaeshin
storeKind: weaviate
storeClass: Experience  # legacy 표시용
```

Weaviate type을 만들 때 실제 collection을 정하는 필드는 `storeClass`가 아니라
`weaviateClassName`이다. POST 생성 API는 이를 직접 입력받지 않고 kind prefix + type
slug로 `ProcChaeshinOrthoCbr` 같은 이름을 생성해 응답한다. `storeClass`만 바꿔서는 새
collection으로 라우팅되지 않는다.

type을 만든 것만으로 챗봇이 쓸 수 있는 것은 아니다. `/memory-access`에서 해당
`ChatbotExperienceTypeLink`를 만들고 필요한 `recall`, `retain`, `delete`, `admin`
권한을 연결한다. 공용 `chaeshin-cbr`과 분리 type 중 무엇을 쓸지는 격리·공유 요구와
collection 운영 비용을 함께 보고 결정한다.

Monitoring이 지원하는 backend 역할은 다음과 같다. 이것은 Chaeshin이 모두 사용한다는
뜻이 아니라 ExperienceType의 선택지다.

| `storeKind` | 적합한 용도 | 현재 mirror 방식 |
|---|---|---|
| `weaviate` | semantic/hybrid procedural retrieval | Weaviate + PostgreSQL |
| `postgres` | 관계 무결성과 SQL 조회가 우선인 데이터 | PostgreSQL only |
| `mongodb` | 자유 schema의 대량 event/log | MongoDB + PostgreSQL |
| `neo4j` | 관계 자체가 핵심인 graph memory | Neo4j adapter + PostgreSQL |

### 14.5 backfill

위키의 legacy backfill 예시는 다음 endpoint를 사용한다.

```bash
curl -X POST http://localhost:3001/api/admin/seed-procedural \
  -H 'x-api-key: <MONITORING_ADMIN_API_KEY>'
```

의도한 처리:

1. ExperienceType upsert
2. AI Hospital type link 생성
3. `experienceType=chaeshin-cbr` 객체 조회
4. `sourceLogId` 없는 객체 skip
5. 이미 같은 `sourceLogId`가 있으면 skip
6. 나머지를 PostgreSQL mirror로 import

이 endpoint가 만드는 AI Hospital type link의 permissions는 빈 배열이다. link row가
있어도 Memory MCP에서는 recall/retain 권한이 없어 deny되므로 `/memory-access`에서
명시적으로 권한을 부여해야 한다.

현재 endpoint는 legacy `Experience` collection을 최대 1,000개 읽으며 dev의
`ProcChaeshinCbr`를 읽지 않는다. 대량/전용 collection backfill 절차로 그대로 믿으면
안 된다. import 전에 PII masking/guardrail도 적용하지 않고, sourceLogId 중복 확인도
unique constraint가 아닌 조회 기반이므로 동시 실행 안전성을 보장하지 않는다.

### 14.6 목표 UI

Review chatbot, 자연어 변경 의도 분류, `?review=pending`, `?binding=unlinked`, 전체
tree를 보며 safe unlink하는 흐름은 위키의 목표 운영 모델이다. 현재 production UI는
bool 상태와 기본 CRUD 중심이며 독립 CaseBinding/review workflow가 완성되지 않았다.

---

## 15. 로컬 개발과 MCP API

### 15.1 설치와 실행

코어 테스트/MCP 개발:

```bash
cd /bananatouch/chaeshin
uv sync --extra dev
uv run pytest tests/ -v --tb=short
```

OpenAI/Chroma/Weaviate/Gradio 예제까지 모두 설치하려면:

```bash
uv sync --all-extras
uv run python -m examples.cooking.chef_agent
```

Claude Code 자동 등록:

```bash
uv run chaeshin setup claude-code --scope project
```

수동 설정의 핵심 entrypoint는 `chaeshin-mcp`다.

```json
{
  "mcpServers": {
    "chaeshin": {
      "command": "uv",
      "args": ["--directory", "/bananatouch/chaeshin", "run", "chaeshin-mcp"]
    }
  }
}
```

PyPI distribution에서 실행한다면 `uv tool run --from chaeshin chaeshin-mcp` 형태를
쓴다. `uv tool run chaeshin-mcp`는 console script 이름을 distribution 이름으로
해석해 재현되지 않는다. 현재 CLI의 uvx 자동등록 branch도 이 잘못된 명령을 생성하므로
등록된 config를 확인해야 한다.

프로젝트별 저장소:

```bash
export CHAESHIN_STORE_DIR=/absolute/path/to/project/.chaeshin
```

문서에 남은 작성자 개인 `/Users/...` 경로는 사용하지 않는다.

### 15.2 AI Hospital API 최소 예시

Hospital의 `/api/retain`과 `/api/retrieve`는 현재 session cookie로 보호된다. 기존 위키의
cookie 없는 curl은 배포 설정에서 401이 날 수 있으므로 인증된 세션을 함께 보낸다.

```bash
curl -X POST http://localhost:3000/api/retain \
  -H 'content-type: application/json' \
  -H 'cookie: ai_hospital_session=<SESSION_JWT>' \
  -d '{
    "request": "야간 근무 T2DM 신환 초진 관리 계획",
    "category": "diabetes-intake",
    "keywords": ["T2DM", "야간근무", "초진"],
    "toolGraph": {
      "nodes": [
        {"id": "intake", "tool": "lifestyle_intake"},
        {"id": "risk", "tool": "risk_stratify"},
        {"id": "plan", "tool": "care_plan"}
      ],
      "edges": [
        {"from_node": "intake", "to_node": "risk"},
        {"from_node": "risk", "to_node": "plan"}
      ]
    },
    "status": "pending",
    "layer": "L3",
    "source": "council_simulation",
    "waitMode": "deadline"
  }'
```

```bash
curl -X POST http://localhost:3000/api/retrieve \
  -H 'content-type: application/json' \
  -H 'cookie: ai_hospital_session=<SESSION_JWT>' \
  -d '{
    "request": "야간 3교대 당뇨 신환 식단과 운동 계획",
    "topK": 3,
    "layer": "L3",
    "threshold": 0.35
  }'
```

category/keywords는 retrieve에서 생략할 수 있다. layer는 실제 후처리/DB filter이고,
Weaviate 후보가 Hospital DB와 결합되지 않으면 PostgreSQL fallback으로 내려간다.
현재 `/api/retrieve` 응답은 score와 Case의 id/layer/request/category/status/keywords/
userSatisfaction만 반환하고 `toolGraph`를 누락한다. 이 API 응답만으로는 찾은 절차를
실행에 재사용할 수 없으므로 계약 보강이 필요하다.

### 15.3 MCP 도구 14개

위키의 도구 목록은 일부 신규 version 도구를 빠뜨린다. 실제 decorator 기준 목록은
다음 14개다.

| 도구 | 용도 |
|---|---|
| `chaeshin_retrieve` | 성공/실패/pending 유사 Case 검색, parent/child 선택 로드 |
| `chaeshin_retain` | graph를 pending Case로 저장하고 계층 연결 |
| `chaeshin_update` | 기존 section의 얕은 필드 patch |
| `chaeshin_revise` | ToolGraph 교체, snapshot, orphan cascade |
| `chaeshin_history` | revision chain 조회 |
| `chaeshin_diff` | 두 version의 node/edge diff |
| `chaeshin_revert` | index 또는 tag가 가리키는 graph를 새 revision으로 복원 |
| `chaeshin_blame` | 현재 node가 들어온 revision 추적 |
| `chaeshin_tag` | HEAD에 tag 생성 또는 tag 목록 조회 |
| `chaeshin_delete` | Case 삭제. child link는 자동 정리하지 않음 |
| `chaeshin_verdict` | success/failure 및 note/satisfaction 기록 |
| `chaeshin_stats` | Case/version/layer/status/deadline/event 통계 |
| `chaeshin_feedback` | 자연어 feedback log와 count 기록 |
| `chaeshin_decompose` | 호스트 AI용 분해 context와 retain protocol 반환 |

실제 Python signature와 기본값은 다음과 같다. 문자열 목록은 쉼표로 구분한다.

| 도구 | 인자와 기본값 |
|---|---|
| retrieve | `query`, `category=""`, `keywords=""`, `top_k=3`, `top_k_failures=3`, `min_similarity=0.5`, `include_children=False`, `include_parent=False`, `min_feedback_count=0` |
| retain | `request`, `graph`, `category=""`, `keywords=""`, `summary=""`, `parent_case_id=""`, `parent_node_id=""`, `difficulty=0`, `child_case_ids=""`, `wait_mode="deadline"`, `deadline_seconds=7200` |
| update | `case_id`, `patch` |
| revise | `case_id`, `graph`, `reason=""`, `cascade=True` |
| history | `case_id` |
| diff | `a_case_id`, `b_case_id` |
| revert | `case_id`, `to_index=-1`, `tag=""`, `reason=""`, `cascade=True`; tag가 index보다 우선 |
| blame | `case_id` |
| tag | `case_id`, `name=""`; 빈 name은 목록 조회 |
| delete | `case_id`, `reason=""` |
| verdict | `case_id`, `status`, `note=""`, `satisfaction=0.0` |
| stats | 인자 없음 |
| feedback | `case_id`, `feedback`, `feedback_type="auto"` |
| decompose | `query`, `tools=""`, `max_depth=4`; 최대 6으로 clamp |

retrieve의 일반 응답 shape는 다음과 같다. 각 Case에는 request/category/layer/graph/outcome과
선택적으로 parent/children, wait, feedback, difficulty, revision 정보가 붙는다.

```json
{
  "search": {"mode": "lexical", "keywords": ["chaeshin", "revise"]},
  "successes": [
    {
      "case_id": "case-1",
      "similarity": 0.82,
      "request": "절차 그래프 수정",
      "category": "bug-fix",
      "layer": "L1",
      "graph": {"nodes": [], "edges": []},
      "outcome": {
        "status": "success",
        "success": true,
        "satisfaction": 0.9,
        "error_reason": "",
        "verdict_note": "검증 완료",
        "verdict_at": "2026-08-26T12:00:00"
      }
    }
  ],
  "failures": [],
  "pending": [],
  "total_in_store": 12
}
```

세 버킷이 모두 비면 5.4장에서 설명한 대로 배열이 없는 별도 shape가 온다.
retain은 계층 link 뒤 계산한 layer/depth와 다음 행동을 반환한다.

```json
{
  "status": "saved",
  "case_id": "4d5b1d7a-...",
  "outcome_status": "pending",
  "layer": "L1",
  "depth": 0,
  "parent_case_id": null,
  "wait_mode": "deadline",
  "deadline_at": "2026-08-26T14:00:00",
  "next_action": "verdict를 받으면 chaeshin_verdict 호출",
  "total_cases": 12
}
```

주요 변경 도구의 응답 계약:

| 호출 | 핵심 응답 |
|---|---|
| update | `status=updated`, `case_id`, `changed_fields` |
| revise | stable `case_id`, `snapshot_case_id`, `revision_index`, node diff, `orphaned_children`, `next_action` |
| verdict | `status=verdict_recorded`, `outcome_status`, `verdict_at` |
| decompose | `similar_cases`, `layer_schema`, `retain_protocol`, `estimated_difficulty`, `should_decompose`, `next_action` |
| stats | `total_cases`, `total_versions`, `total_snapshots`, `db_path`, `has_embeddings`, `categories`, `layers`, `outcome_status`, `overdue_pending`, `event_count` |

MCP graph 입출력에는 중요한 fidelity 제한이 있다. `chaeshin_retain`은 node의
`id/tool/params_hint/note`와 edge의 `from_node/to_node/condition`만 재구성한다. 따라서
node의 `input_schema/output_schema`, edge의 `action/priority/note`, ToolGraph의
`parallel_groups/entry_nodes/max_loops`는 전달해도 유실된다. `chaeshin_revise`는 알려진
node/edge 필드는 더 보존하지만 top-level 세 필드는 역시 버린다. retrieve formatter도
축약 필드만 반환한다. 이 경로를 full-fidelity ToolGraph round-trip으로 가정하면 안 된다.

다른 경로도 full fidelity가 아니다.

- GSX2 direct serializer는 node에서 `id/tool/note`, edge에서 `from/to`만 남겨
  params/schema/condition/action/priority/note와 모든 ToolGraph top-level 필드를 잃는다.
- AI Hospital retain Zod schema는 node의 params_hint와 edge의 condition/action까지는
  받지만 node input/output schema, edge priority/note, top-level 필드를 strip한다.
- GSX2 monitoring report의 `from/to` edge는 core Weaviate loader가 복원하지 못한다.

따라서 저장 경계를 하나 통과할 때마다 허용 필드 집합을 명시하고 round-trip test를 둬야
한다.

주요 사용 원칙:

- 3개 이상의 tool call이 예상되면 먼저 retrieve한다.
- 복잡한 tree가 필요할 때만 `include_children=True`를 쓴다.
- 실제로 수행한 절차만 retain한다.
- 로컬 MCP에서는 성공/실패를 추측하지 않고 pending으로 둔다.
- 단순 metadata/outcome 변경은 update, graph 구조 변경은 revise다.
- failure는 삭제보다 warning 보존을 우선한다.
- canonical edge는 `from_node`/`to_node`를 사용한다.

### 15.4 CLI 범위

현재 CLI는 Claude Code/Claude Desktop/OpenClaw setup, auto-learn, stats, retrieve, seed를
제공한다. `scripts/run-local.sh`가 안내하는 `chaeshin serve`, `anticipate` 명령은 실제
CLI에 없다. OpenClaw bridge는 legacy `cases.json`과 별도 success/failure 추론을 쓰며,
stats의 정의되지 않은 변수 참조도 있어 로컬 MCP 정본과 같은 경로로 보면 안 된다.

### 15.5 cold-start seed

ToolGraph는 두 시점에 만들어진다.

| 시점 | 생성 방식 |
|---|---|
| offline seed | LLM 한 호출이 사용자 시나리오 하나와 graph 하나를 JSON으로 생성 |
| runtime | ReAct/tool trace를 실제 실행 순서대로 graph로 재구성 |

seed 생성 prompt는 `topic`, 실제 tool allowlist, 선택적 1-shot sample,
`avoid_themes`를 받는다. node는 1~6개로 제한하고 allowlist 밖 tool은 검증에서
거부한다. 처음 도메인을 열 때 손으로 검수한 5~10개 sample을 주면 분포를 잡기 쉽다.

```bash
uv run chaeshin seed generate \
  --topic 'T2DM 초기 상담' \
  --tools 'lifestyle_intake,risk_stratify,care_plan' \
  --count 5

uv run chaeshin seed list
uv run chaeshin seed promote --all
```

seed는 별도 `seed.db`에서 생성·dedup한 뒤 새 id로 main `chaeshin.db`에 promote한다.
`generate`에는 `OPENAI_API_KEY`가 필요하다. import/export도 지원한다.

근거: [scenario_prompt.py](/bananatouch/chaeshin/chaeshin/seed/scenario_prompt.py:12),
[seed_cmd.py](/bananatouch/chaeshin/chaeshin/cli/seed_cmd.py:67).

---

## 16. 운영 배포와 환경변수

### 16.1 주요 환경변수

| 변수 | 사용처 |
|---|---|
| `CHAESHIN_STORE_DIR` | 로컬 MCP SQLite root |
| `CHAESHIN_DB_PATH` | 로컬 monitor가 읽을 SQLite |
| `CHAESHIN_SEED_DB_PATH` | seed staging SQLite override |
| `CHAESHIN_TOOLS_PATH` | 로컬 monitor의 `tools.json` override |
| `CHAESHIN_PROJECT_DIR` | 로컬 monitor가 seed Python subprocess를 실행할 cwd |
| `CHAESHIN_DEMO_PERSIST` | `1/true/yes`면 ReAct demo를 임시 DB 대신 main DB에 저장 |
| `CHAESHIN_LLM_MODEL` | cooking demo/UI의 chat model; MCP OpenAIAdapter에는 자동 반영되지 않음 |
| `CHAESHIN_EMBEDDING_MODEL` | cooking demo/UI의 embedding model; MCP OpenAIAdapter에는 자동 반영되지 않음 |
| `CHAESHIN_STEP_DELAY` | cooking demo 표시 지연 |
| `OPENAI_API_KEY` | 로컬 embedding, GSX2 embedding, Hospital hybrid |
| `WEAVIATE_URL` | GSX2/Hospital Weaviate HTTP |
| `WEAVIATE_GRPC_PORT` | Weaviate gRPC, 기본 50051 |
| `CHAESHIN_WEAVIATE_COLLECTION` | core store collection override |
| `GSX2_CHATBOT_ID` | GSX2 Case 소유 scope |
| `BT_MONITORING_URL` | Experience/manifest 보고 및 조회 |
| `BT_MONITORING_API_KEY` | monitoring 인증 |
| `GUARDRAIL_ENFORCE` | bt-monitoring POST guardrail의 shadow/enforce 모드 |
| `GUARDRAIL_MASK_DISABLE` | true면 bt-monitoring PII masking 비활성화 |
| `MEMORY_MCP_URL` | 서비스용 memory MCP endpoint |
| `MEMORY_MCP_KEY` | `x-mcp-chatbot-key` 인증 |
| `AGENT_REGISTRY_URL` | Hospital monitoring REST fallback |
| `AGENT_REGISTRY_API_KEY` | `x-api-key` 인증 |

GSX2 ExternalSecret에는 현재 `OPENAI_API_KEY`가 보이지 않는다. 다른 주입 경로가 없다면
core Weaviate 검색은 BM25-only로 내려간다. Hospital은 같은 상황에서 Weaviate 검색을
끄고 PostgreSQL fallback을 사용한다.

### 16.2 현재 배포 특성

- Weaviate는 1 replica, `local-path`, 10Gi, anonymous access다.
- 확인된 manifest에는 별도 backup/snapshot/restore 구성이 없다.
- 독립 Chaeshin 서비스와 로컬 monitor는 K8s에 배포되지 않는다.
- medical-council manifest의 `CHAESHIN_API_URL=http://chaeshin`은 실제 Service 없이
  남은 stale 설정이다.
- dev overlay만 `ProcChaeshinCbr`를 명시하므로 다른 환경은 collection drift를 확인해야
  한다.

---

## 17. 알려진 격차와 우선순위

### 17.1 P0 후보

| 문제 | 영향 |
|---|---|
| `CaseMetadata.tags` 이중 선언 | MCP retain 후 tag, UI 표시에서 런타임 오류 가능 |
| 일부 쓰기 경로의 PII masking 우회 | direct Weaviate, PUT, backfill과 POST keywords에 의료·개인 정보가 남을 수 있음 |
| Monitoring PUT의 Weaviate sync no-op | UI 성공 표시와 달리 retrieve는 항상 이전 객체를 봄 |
| `sourceLogId`의 비원자·비고유 처리 | 동시/교차-chatbot 충돌과 Weaviate 중복, 부분 DELETE 가능 |
| pending이 bool 계층에서 failure로 축약 | 미검증 Case가 실패 warning으로 오염 |
| failure/pending에서도 anticipated graph 생성 | 회피해야 할 절차가 추천 tool prior로 승격될 수 있음 |
| REST/direct 경로의 memory 권한 우회 | link에 retain 권한이 없어도 쓰기가 가능 |
| Hospital Case의 tenant 소유권/filter 부재 | 유효 세션이 다른 사용자의 의료 Case를 검색 후보로 볼 수 있음 |
| single replica/local-path와 복구 절차 부재 | node 장애 시 메모리 유실 위험 |

bt-monitoring POST는 일부 payload를 masking하지만 keywords는 제외하고 shadow/fail-open
guardrail을 쓴다. PUT/backfill과 core direct `WeaviateCaseStore.retain()`은 이 보호를
거치지 않는다.

### 17.2 P1 후보

- direct Weaviate retain + monitoring report의 중복 가능성
- Monitoring POST 외부-store-first dual-write의 부분 성공/고아 객체 가능성
- GSX2 monitoring report JSON과 core Case loader의 비호환
- ToolMessage 휴리스틱과 고정 0.85를 실제 사용자 성공/만족으로 저장
- 운영 Weaviate에 hierarchy/revision/verdict 기능 부재
- 자동 migration runner 부재
- Weaviate 초기 cache 1,000개 제한
- chatbot id 최초 해석 실패의 장기 cache
- MCP fallback signature drift와 없는 anticipate tool
- `from/to`와 `from_node/to_node` drift
- Survey 안내 문구는 만족도 75 이상을 성공이라고 설명하지만 실제 feedback 코드는
  40 이상을 성공으로 분류하는 threshold drift
- graph revision 전체 transaction/CAS 부재
- snapshot에 대한 storage-level write guard 부재
- MCP/GSX2/Hospital 경계의 ToolGraph 필드 유실
- executor replan graph 전파 결함
- executor fan-in readiness와 layered modify/aggregation 결함
- 계층 link의 cycle/reparent/parent-node 무결성 검사 부재
- GSX2의 L1/L2/L3 label과 core topology 불일치
- 로컬 Orchestrator/Decomposer의 retrieve 결과가 실행 graph reuse로 이어지지 않음
- Hospital retrieve API가 ToolGraph를 반환하지 않음
- `uv tool run chaeshin-mcp` 자동등록 명령 오류
- Outcome status의 schema-level enum validation 부재
- core package version `0.2.0`과 runtime `__version__=0.1.0` 불일치
- local monitor의 무인증 CRUD와 version chain 우회
- Chroma 재시작 후 기존 collection을 in-memory cache로 hydrate하지 않는 문제

### 17.3 문서에서 현재형으로 쓰면 안 되는 항목

| 항목 | 정확한 상태 |
|---|---|
| 모든 retain은 pending | 로컬 MCP 원칙, GSX2 direct 경로는 즉시 판정 |
| 운영 검색이 3버킷 | core Weaviate/UI는 현재 2버킷 |
| safe unlink | 목표. 현재 코어는 child Outcome을 pending으로 바꿈 |
| run override/variant/correction 분리 | 목표 schema/API |
| 독립 CaseBinding | 미구현 |
| review chatbot 전체 flow | 목표/부분 UI |
| 10 atomic ops/GraphCommit/3-way merge/cherry-pick/squash | 확장 설계 |
| capability registry 전체 | 기본 bridge는 구현, param map/curation은 미구현 |
| Dental formatter 미구현 | 현재 구현됨 |
| 첫 LLM이 항상 retrieve tool 호출 | 표준 엔진은 LLM 전에 자동 retrieve |
| MCP 기본 deadline 14일 | 현재 2시간 |
| production collection은 `Experience` | dev 배포는 `ProcChaeshinCbr` |
| `chatbotId`는 filter 아님 | 현재 core store는 자기 id + `legacy` filter |
| `sourceLogId`면 전체 upsert | PostgreSQL best-effort lookup일 뿐, Weaviate는 중복 insert 가능 |
| Monitoring UI 편집이 retrieve에 즉시 반영 | 현재 PUT의 Weaviate update는 no-op |
| memory-access link가 모든 경로를 보호 | Memory MCP 중심; REST/direct는 우회 |
| GSX2 `retain_l1`은 tool 1회 leaf | 실제 표준 자동 retain은 최소 2-tool trace |

---

## 18. 검증 전략

### 18.1 로컬

현재 CI는 Python 3.10/3.11/3.12에서 `uv sync --extra dev`와 pytest를 실행한다.
테스트는 schema, CaseStore, executor, SQLite, EventLog, pending/verdict, hierarchy,
cascade, version, seed를 중심으로 한다.

추가해야 할 집중 테스트:

- list tags로 retain한 뒤 `chaeshin_tag` 호출
- empty retrieve와 non-empty retrieve의 동일 response shape
- wait_mode/deadline/satisfaction validation
- 재-verdict 정책
- revision 중간 persistence failure의 rollback
- replan graph가 다음 executor loop에 실제 반영되는지
- canonical edge가 GSX2 direct/report/UI를 모두 통과하는지
- capability rewrite가 모든 retain entrypoint에 적용되는지
- self-link/cycle/reparent와 없는 `parent_node_id` 거부
- fan-in node가 모든 predecessor 완료 후에만 READY가 되는지
- MCP/GSX2/Hospital별 ToolGraph round-trip field 보존표
- 임의 Outcome status를 모든 입력 경계에서 거부하는지

### 18.2 운영 dev cluster

반드시 E2E로 확인할 항목:

1. `ProcChaeshinCbr` direct 저장과 PostgreSQL Experience report의 중복 여부
2. pending이 failure로 변환되지 않는지
3. chatbot cuid/legacy scope 격리
4. UI 수정 후 다음 retrieve에 새 값이 반영되는지
5. L1/L2/L3의 PostgreSQL mirror 일관성
6. direct Weaviate path의 PII masking
7. 1,000건을 넘긴 뒤 검색 recall
8. pod restart와 node 장애 후 복구
9. `OPENAI_API_KEY`가 실제 GSX2 pod에 존재하는지와 BM25 fallback metric
10. MCP-only backend의 retain/anticipate 계약
11. Monitoring PUT 뒤 실제 Weaviate 객체와 검색 결과가 바뀌는지
12. 같은 sourceLogId의 동시/교차-chatbot POST와 재-verdict 중복 수
13. POST keywords, PUT, backfill, direct retain의 PII 잔존 여부
14. anticipated graph가 success Case에서만 만들어지는지
15. GSX2 monitoring report를 core loader가 다시 읽을 수 있는지
16. Hospital retrieve 응답이 실행에 필요한 ToolGraph를 제공하는지

### 18.3 턴 단위 운영 진단

한 대화가 기대와 다르게 행동했을 때는 Langfuse trace, bt-monitoring access log,
애플리케이션 로그를 같은 trace/session id로 맞춰 다음 순서로 본다.

| 점검 | 확인할 내용 |
|---|---|
| retrieve 실행 | 자동 경로는 첫 LLM 전 `chaeshin_hint` graph node, 명시 경로는 `memory_retrieve_similar` tool span |
| 검색 품질 | top-K score 분포와 cutoff 아래로 모두 버려졌는지 |
| prompt 전달 | 자동 hint block 또는 명시 tool result가 예상 Markdown이고 raw/untrusted payload가 그대로 섞이지 않았는지 |
| 행동 영향 | recalled graph의 첫 live tool과 실제 다음 tool call이 일치하거나, 달라졌다면 현재 조건상 이유가 있는지 |
| 상태 분배 | success/failure/pending 비율과 운영 2-bucket 경로에서 pending이 warning으로 섞였는지 |
| 학습 완료 | 종료 뒤 retain이 발생했고 stable case/source id 및 trace id가 연결됐는지 |
| 검토 SLA | `overdue_pending`과 deadline 경과 pending 큐가 증가하는지 |

명시 tool span이 없다는 사실만으로 자동 retrieve 실패라고 판단하면 안 된다. 표준
`ExpertAgentEngine`은 LLM이 tool을 고르기 전에 `chaeshin_hint` node에서 검색한다. 반대로
Medical Council처럼 auto adapter가 없는 서비스는 명시 memory tool span이 실제 검색의
근거다.

현재 조사 환경에는 `uv`/`pytest`가 없어 test suite는 실행하지 못했다. 이 문서는
정적 코드 교차검증 결과이며, 운영 데이터 쓰기나 배포는 수행하지 않았다.

---

## 19. Mem^p 연구 배경

위키의 논문 페이지는 Mem^p를 Build/Retrieve/Update 3축으로 정리한다.

논문 메타데이터와 실험 범위:

| 항목 | 내용 |
|---|---|
| 논문 | Fang et al., *Mem^p: Exploring Agent Procedural Memory* |
| 게재 | ACL 2026 Findings |
| arXiv | v1 2025-08-08, 위키가 확인한 최신판 v4 2026-04-15 |
| benchmark | TravelPlanner, ALFWorld |
| 주요 모델 | GPT-4o, Claude-3.5-Sonnet, Qwen2.5-72B |

### 19.1 논문의 핵심

- **Build** 비교군은 No Memory, Trajectory, Script, Proceduralization이다. raw
  trajectory와 추상화한 script를 함께 저장하는 Proceduralization이 가장 우수했다.
- **Retrieve** 비교군은 Random, Query, AveFact다. AveFact는 여러 관점의 fact로 query와
  memory를 확장해 비교하며, 단순 query embedding보다 더 좋았다.
- **Update** 비교군은 Vanilla, Validation, Adjustment다. Vanilla는 모든 경험을 append하고,
  Validation은 성공 경험만 남기며, Adjustment는 실패 원인과 기존 기억을 함께 반성해
  기억 자체를 수정한다. 마지막 방식이 가장 우수했다.
- 검색 개수는 대략 `k≈5`가 적절했다.
- 강한 모델이 만든 기억을 약한 모델로 전이할 수 있었다.

위키가 인용한 TravelPlanner 결과:

| 모델/설정 | common-sense | hard constraint | 평균 step |
|---|---:|---:|---:|
| GPT-4o, No Memory | 71.93 | 12.88 | 17.84 |
| GPT-4o, Random retrieve | 73.20 | 11.50 | 16.30 |
| GPT-4o, Query retrieve | 74.80 | 9.10 | 15.90 |
| GPT-4o, AveFact retrieve | 76.02 | 8.25 | 14.64 |
| GPT-4o, Proceduralization | 79.94 | 9.76 | 14.62 |
| Claude-3.5-Sonnet, No Memory | 63.49 | 33.06 | 18.84 |
| Claude-3.5-Sonnet, Proceduralization | 65.46 | 30.14 | 15.29 |
| Qwen2.5-72B, No Memory | 56.57 | 7.34 | 18.32 |
| Qwen2.5-72B, Proceduralization | 63.82 | 14.19 | 17.94 |

추가로 위키는 다음을 요약한다.

- ALFWorld 사례: 17 step → 8 step, token 약 21% 감소
- Adjustment는 Validation 대비 최종 성능 약 +0.7%p, 평균 step 약 14 감소
- GPT-4o 기억을 Qwen2.5-14B로 전이: 완료율 약 +5%p

이는 [Mem^p 논문](https://arxiv.org/abs/2508.06433)의 결과이며 Chaeshin 운영
benchmark가 아니다.

### 19.2 Chaeshin과의 차이

| Mem^p | Chaeshin |
|---|---|
| 자연어 trajectory + script | 실행 가능한 정형 ToolGraph |
| 얕은 2-tier memory | 별도 Case로 이어진 L1~L4+ |
| 논문 중심의 build/retrieve/update | delayed judgment, failure warning, HITL, revision, 조직 거버넌스까지 지향 |

Chaeshin은 Mem^p의 “절차 기억이 성능과 비용에 도움을 준다”는 방향을 공유하지만,
구조적 실행·수정·배포 모델을 더 강하게 가져가려는 구현이다.

### 19.3 논문의 한계와 Chaeshin에서의 해석

- 명시적 reward에 의존하므로 지연되거나 잡음이 큰 의료 outcome에는 그대로 적용하기
  어렵다. pending/verdict와 HITL이 필요한 이유다.
- retrieval 비교가 제한적이고, build→retrieve→update의 연속 운영 loop는 부분적으로만
  검증됐다.
- 자연어 memory는 바로 실행할 수 없고 tool schema drift를 보장하지 않는다. Chaeshin의
  ToolGraph와 capability 변환은 이 공백을 메우려는 설계다.
- 계층 구조와 실패의 인과 분석이 얕고, 조직 권한·감사·승인 같은 governance를 다루지
  않는다.
- common-sense 성능 개선이 hard-constraint 개선을 항상 뜻하지는 않는다. 위 표처럼 일부
  설정에서는 제약 점수가 악화되므로 전체 성공률 하나만으로 retain 정책을 정하면 안 된다.

---

## 20. 권장 위키 정보 구조

현재 sidebar 순서는 학습 순서와 다르다. 개발자 문서는 다음 순서가 이해하기 쉽다.

1. **개요와 상태 표** — 이 문서의 1~2장
2. **한 턴 따라가기** — 자동 경로와 명시 tool 경로를 모두 설명
3. **Case/ToolGraph 데이터 모델** — 3장
4. **Retrieve/Retain/Verdict** — 5~6장
5. **Layer/Executor** — 7~8장
6. **Revise/Version** — 9~10장
7. **Tool drift/capability** — 11장
8. **에이전트 통합** — 12장
9. **저장소/Vector DB** — 13장
10. **Monitoring/권한** — 14장
11. **빠른 시작/MCP** — 15장
12. **배포/운영/테스트** — 16~18장
13. **연구 배경** — 19장

각 페이지 상단에 다음 블록을 두는 것을 권장한다.

```text
상태: 현재·로컬 | 현재·운영 | 목표
정본 코드: <path>
마지막 코드 확인: <commit/date>
알려진 격차: <link>
```

---

## 21. 원문 페이지 완전성 표

다음은 조사한 `chaeshin` 전체 하위 트리다. 루트와 `papers`는 빈 목차이며, 나머지
13개 본문 내용은 이 가이드에 재배치했다.

| 원문 | 이 가이드의 대응 장 |
|---|---|
| [chaeshin 루트](https://docs.bananatouch.com/s/bt-agents/p/chaeshin-zCAi5fp80G) | 빈 목차 → 전체 가이드 |
| [Chaeshin 소개](https://docs.bananatouch.com/s/bt-agents/p/chaeshin-OLeFZlXY0I) | 1, 10, 19 |
| [한 턴 따라가기](https://docs.bananatouch.com/s/bt-agents/p/-ZjbsL4hLRR) | 4, 5, 6 |
| [케이스 동작 방식](https://docs.bananatouch.com/s/bt-agents/p/-cU88bpVRNT) | 1, 6, 7, 9 |
| [케이스 필드 정의서](https://docs.bananatouch.com/s/bt-agents/p/-N0X777GPxR) | 3 |
| [Vector DB 데이터 정의서](https://docs.bananatouch.com/s/bt-agents/p/vector-db-9I3yPzw7GR) | 5, 13 |
| [에이전트 통합](https://docs.bananatouch.com/s/bt-agents/p/-p8wLy06JIX) | 2, 12, 16 |
| [빠른 시작](https://docs.bananatouch.com/s/bt-agents/p/-h8WHG4fRFz) | 15 |
| [MCP 도구](https://docs.bananatouch.com/s/bt-agents/p/mcp-cW6yVX9aGJ) | 15 |
| [Monitoring UI](https://docs.bananatouch.com/s/bt-agents/p/monitoring-ui-u4mmAqz8hX) | 14 |
| [절차 메모리 수정 Q&A](https://docs.bananatouch.com/s/bt-agents/p/q-a-hJaegweRAW) | 9 |
| [케이스 절차 버전 관리](https://docs.bananatouch.com/s/bt-agents/p/-ckKjSWeAEF) | 10 |
| [Tool 변동 대응 설계](https://docs.bananatouch.com/s/bt-agents/p/tool-HbLm5rsPtT) | 11 |
| [papers](https://docs.bananatouch.com/s/bt-agents/p/papers-tn8JQ749Jx) | 빈 목차 → 19 |
| [Mem^p 논문 정리](https://docs.bananatouch.com/s/bt-agents/p/mem-p-exploring-agent-procedural-memory-MTPBqJECy3) | 19 |

반복 참조되는 루트 밖 문서:

- [Memory MCP](https://docs.bananatouch.com/s/bt-agents/p/memory-mcp-wFzDiV4PqD)
- [AI Hospital 아키텍처](https://docs.bananatouch.com/s/bt-agents/p/-RHd7MykIjA)
- [Tool Registry P0~P3](https://docs.bananatouch.com/s/bt-agents/p/tool-registry-p0-p3-aFtPP8sxKQ)
- [Procedural memory 블로그](https://docs.bananatouch.com/s/dev-blog/p/procedural-memory-llm-mcRgMtwgsg)

---

## 22. 코드 읽기 지도

| 관심사 | 정본 또는 핵심 구현 |
|---|---|
| Case/ToolGraph/Outcome | [schema.py](/bananatouch/chaeshin/chaeshin/schema.py:82) |
| local retrieve/retain/hierarchy/version | [case_store.py](/bananatouch/chaeshin/chaeshin/case_store.py:43) |
| search normalization/scoring | [search.py](/bananatouch/chaeshin/chaeshin/search.py:1) |
| graph runtime | [graph_executor.py](/bananatouch/chaeshin/chaeshin/graph_executor.py:35) |
| planner/decompose/feedback prompts | [planner.py](/bananatouch/chaeshin/chaeshin/planner.py:33) |
| SQLite | [sqlite_backend.py](/bananatouch/chaeshin/chaeshin/storage/sqlite_backend.py:42) |
| Claude Code MCP | [mcp_server.py](/bananatouch/chaeshin/chaeshin/integrations/claude_code/mcp_server.py:198) |
| core Weaviate | [weaviate.py](/bananatouch/chaeshin/chaeshin/integrations/weaviate.py:46) |
| GSX2 adapter | [chaeshin_adapter.py](/bananatouch/gsx2-chain/libs/gsx2_agent/gsx2_agent/chaeshin_adapter.py:113) |
| GSX2 engine flow | [engine.py](/bananatouch/gsx2-chain/libs/gsx2_agent/gsx2_agent/engine.py:222) |
| capability bridge | [capability_registry_bridge.py](/bananatouch/gsx2-chain/libs/gsx2_agent/gsx2_agent/capability_registry_bridge.py:1) |
| bt-monitoring Experience API | [route.ts](/bananatouch/bt-agent-monitoring/src/app/api/experiences/route.ts:65) |
| production Chaeshin UI | [ChaeshinTab.tsx](/bananatouch/bt-agent-monitoring/src/components/chaeshin/ChaeshinTab.tsx:39) |
| Hospital Case schema | [schema.prisma](/bananatouch/bt-agent-hospital/prisma/schema.prisma:72) |
| Hospital retain/sync | [weaviate.ts](/bananatouch/bt-agent-hospital/src/lib/weaviate.ts:231) |
| deployment wiring | [gsx2 kustomization](/bananatouch/infra/k8s/apps/gsx2-chain/kustomization.yaml:76) |
