# Chaeshin Architecture Invariants

## 불변식 요약

| ID | 반드시 지켜야 하는 규칙 |
|---|---|
| `INV-001` | **Layer 1은 항상 ToolGraph다.** Layer 2 이상은 바로 아래 Layer의 Case 약 5~7개를 묶은 Procedure다. |
| `INV-002` | **검색할 때에는 모든 Layer를 함께 검색한다.** Vector/lexical seed를 Ontology 관계로 확장하고 현재 Situation·Tool·정책으로 재정렬하며, Layer를 먼저 예측해 검색 범위를 제한하지 않는다. |
| `INV-003` | **콘텐츠, 근거, 호환성, 인덱스 버전을 분리한다.** 각 변경 원인과 이력을 독립적으로 추적한다. |
| `INV-004` | **저장, 판정, 게시, 검색 권한을 분리한다.** 하나의 주체가 모든 상태를 임의로 확정하지 않는다. |
| `INV-005` | **정본 메모리 모델은 온톨로지다.** Case, Situation, Procedure, ToolGraph와 revision 관계를 명시적으로 표현한다. |
| `INV-006` | **Tool 선택은 Situation에 따라 달라진다.** Situation은 부분 관측된 belief로 다루며, Tool Observation 뒤 다시 구성해 다음 Tool을 새로 선택한다. |

이 문서는 Chaeshin의 코드, 프롬프트, 논문, 예제와 그림이 반드시 함께 지켜야
하는 아키텍처 불변식의 정본이다. 다른 문서나 현재 구현이 이 파일과 충돌하면
이 파일을 기준으로 수정한다.

- 상태: **Normative**
- 최초 기록: 2026-08-30
- 변경 원칙: 불변식을 바꾸는 변경은 코드와 논문을 먼저 고치는 방식이 아니라,
  이 문서에서 변경 이유와 영향을 합의한 뒤 함께 반영한다.

## 기본 규칙

1. Layer 1은 항상 실제 Tool node와 control-flow edge로 구성된 ToolGraph다.
2. Layer 2 이상은 바로 아래 Layer의 Case 약 5~7개를 묶은 Procedure다.
3. 검색할 때에는 검색 가능한 모든 Layer를 하나의 후보 공간에서 함께 검색한다.
4. 같은 사용자 요청이라도 현재 Situation에 따라 ReAct가 선택하는 Tool은 달라진다.
5. Tool 실행 결과를 Observation으로 받은 뒤에는 현재 Situation을 다시 파악하고,
   갱신된 Situation을 기준으로 다음 Tool을 새로 선택한다.

## INV-001 — Layer 1은 항상 ToolGraph다

`Layer 1 (L1)`은 Chaeshin 계층의 실행 기반이며 항상 **ToolGraph** 형태다.

- L1은 “Tool 하나”와 동의어가 아니다. 하나 이상의 실제 Tool node와 node 사이의
  순서, 조건, 분기, 병렬 실행, 반복을 나타내는 edge를 가질 수 있다.
- L1의 각 node는 Host가 실제로 호출할 수 있는 Tool과 그 입력 힌트를 가리킨다.
- L1 아래에 더 낮은 추상화 계층은 없다. Procedure를 계속 펼쳤을 때 도달하는 실행
  근거가 L1 ToolGraph다.
- Layer 수에는 고정된 상한이 없다.

`Layer 2 (L2)`부터 `Layer N (LN)`까지는 **하위 Case를 묶은 Procedure 계층**이다.

- Chaeshin 고유 저장 유형의 정식 명칭은 `Procedure(절차)`다. `Skill`은 저장
  유형명이나 Layer 이름으로 사용하지 않는다. 단, Graph-of-Skills, Voyager의
  skill library, OpenClaw의 `SKILL.md`처럼 외부 시스템의 고유 명칭은 원문대로
  표기한다.
- Procedure는 원칙적으로 바로 아래 Layer의 Case 약 5~7개를 순서·조건과 함께
  묶은 재사용 가능한 절차다.
- L2 Procedure는 5~7개의 L1 ToolGraph Case를 묶고, L3 이상의 Procedure는
  5~7개의 바로 아래 Layer Procedure Case를 묶는다.
- ProcedureStep은 바로 아래 Layer의 Procedure 또는 L1 ToolGraph Case를 참조한다.
- 상위 Layer 자체를 곧바로 실제 Tool 목록으로 간주해 실행하지 않는다. 필요한
  Procedure를 재귀적으로 펼치면 최종적으로 L1 ToolGraph에 도달한다.
- 현재 저장 형식에서 모든 Case가 `solution.tool_graph` 컨테이너를 사용하더라도,
  L1의 실행 ToolGraph와 L2 이상의 Procedure 의미를 동일한 개념으로 설명해서는 안
  된다. 스키마는 이 의미 차이를 명시적으로 보존해야 한다.

5~7개는 기본 branching factor다. 7개를 초과하면 한 단계 더 분해하는 것이
원칙이며, 5개 미만이거나 예외적으로 7개를 초과하는 Procedure는 그 이유를
provenance에 남기고 validator warning을 발생시킨다.

정규 형태는 다음과 같다.

```text
LN   Procedure / 목표 수준 절차
 ⋮
L3   Procedure / 업무 수준 절차
L2   Procedure / L1 ToolGraph 5~7개를 묶은 절차
L1   ToolGraph / 실제 Tool node + control-flow edge
```

금지되는 해석:

- `L1 = 단일 Tool 호출`
- `모든 Layer는 의미상 동일한 ToolGraph`
- 상위 ProcedureStep을 등록된 Tool인 것처럼 직접 호출
- Layer를 고정된 3단계 또는 4단계로 제한

## INV-002 — 검색은 모든 Layer를 함께 대상으로 한다

사용자 query가 들어오면 first-stage retrieval은 `L1 ... LN`의 현재 검색 가능한
메모리를 **하나의 후보 공간에서 동시에 검색**한다.

- query를 먼저 특정 Layer로 분류한 뒤 그 Layer만 검색하지 않는다.
- lexical, embedding, graph 또는 hybrid recall index에는 모든 Layer가 들어간다.
- 특정 Layer에서 seed가 발견돼도 검색 결과에는 다른 Layer의 관련 Procedure와
  ToolGraph가 함께 경쟁할 수 있다.
- 전체 Layer recall 뒤에는 parent/child, anchor, dependency 관계를 따라 필요한
  상·하위 구조를 확장할 수 있다. 이 structural expansion은 “모든 Layer 동시
  검색”을 대체하지 않는다.
- 결과에는 최소한 `case_id`, `layer`, `memory_kind`, `ProblemFeatures`, ToolGraph
  또는 Procedure 구조, `outcome`, provenance가 포함되어야 한다.
- Layer는 검색 필터가 아니라 결과 해석과 구조 확장을 위한 속성이다.

### 정규 검색 파이프라인

정규 검색 흐름은 다음과 같다. 사용자 질문만 embedding하지 않고 현재
`RuntimeSituationSnapshot`의 확인된 claim, unknown, 목표와 hard constraint를 함께
검색 표현으로 만든다.

```text
사용자 질문 + 현재 Situation
  → QueryProfile 정규화 + Embedding 생성
  → 모든 Layer의 검색 가능한 Case를 Vector/lexical 검색
  → 관련 Procedure/ToolGraph seed 확보
  → Ontology 관계로 상·하위 Case, 선행 조건, 대안, revision, 실패 이력 확장
  → 현재 Situation·Tool 가용성·정책·outcome·validity로 filter 및 재정렬
  → closure와 token budget을 만족하는 제한된 Chaeshin Context
  → ReAct가 참고하여 다음 Tool 하나를 직접 선택
```

| 단계 | 주요 입력 | 처리 | 출력 |
|---|---|---|---|
| 1. Query profiling | 사용자 질문, `RuntimeSituationSnapshot`, 목표, constraint, available Tools | 자연어와 구조 필드를 정규화하고 embedding/lexical query를 만든다. | `QueryProfile`, query vector |
| 2. All-layer recall | query vector, lexical query, 검색 가능한 L1...LN index | active, tenant, ACL, as-of 조건을 먼저 만족하는 모든 Layer Case를 동일 후보 공간에서 검색한다. | scored Case candidates |
| 3. Seed formation | vector·lexical candidates | 중복을 합치되 Layer별 결과를 미리 제거하지 않고 Procedure와 ToolGraph seed를 보존한다. | cross-layer seeds |
| 4. Ontology expansion | seed Case IRI와 현재 Situation | `expandsTo`, `anchoredAt`, `dependsOn`, `alternativeTo`, `supersedes`, `conflictsWith`, outcome 관계를 제한된 깊이로 탐색한다. | 구조적으로 닫힌 candidate subgraph |
| 5. Filter and rerank | candidate subgraph, Situation claims, available Tools, policy, validity, outcomes | hard constraint와 governance를 적용하고 semantic·state·tool·policy·evidence 점수를 함께 사용한다. | ordered evidence candidates |
| 6. Context packing | ordered candidates, mandatory closure, token/risk budget | 관련 branch만 hydrate하고 포함·누락 이유와 provenance를 기록한다. | bounded `ContextBundle` |
| 7. ReAct use | `ContextBundle`, 최신 Observation, available Tools | 검색 결과를 plan으로 실행하지 않고 다음 Tool 하나를 직접 선택한다. | next Tool call 또는 사용자 질문 |

Vector similarity는 seed를 만드는 신호이지 최종 실행 판단이 아니다. Ontology
expansion은 vector recall 이후에 질문에 직접 등장하지 않은 prerequisite와 관련
Case를 보충하지만, 처음부터 모든 Layer를 검색한다는 원칙을 대체하지 않는다.

재정렬은 최소한 다음 신호를 분리해 기록해야 한다.

```text
score_vector = {
  semantic_similarity,
  lexical_match,
  situation_compatibility,
  tool_availability,
  policy_compatibility,
  outcome_evidence_quality,
  validity,
  relation_distance,
  freshness
}
```

하나의 합산 점수만 저장하지 않고 위 score vector와 filter 사유를
`RetrievalTrace`에 남겨 같은 query와 Situation에서 검색 결과를 재현할 수 있어야
한다.

금지되는 해석:

- `query → Layer 예측 → 해당 Layer만 검색`
- 항상 최상위 Layer 또는 L1만 검색
- similarity 1등 graph를 그대로 실행
- vector 검색에서 찾은 seed만 반환하고 ontology closure를 생략
- ACL·tenant·quarantine 조건을 ranking 이후의 soft score로만 처리
- 검색 결과를 별도 Planner의 확정 실행 계획으로 취급

## 저장 요소와 의미

Chaeshin은 실제 사용자 작업인 `Task`와, 재사용하기 위해 저장한 절차 메모리인
`Case`를 구분한다.

```text
Task       = 이번에 실제로 들어온 하나의 사용자 작업
Case       = 검색·재사용·버전 관리되는 하나의 절차 메모리
Situation  = Task 또는 Case가 놓인 의미적·실행 시점 상황
```

한 Task가 여러 Layer의 Case를 만들거나 여러 Case를 참고할 수 있다. 이때 Case들이
`task_id` 값을 복사해 소유하는 것이 아니라, ontology에서 하나의 Task individual을
`derivedFromTask` 또는 `usedCase` 관계로 참조한다.

### 핵심 저장 요소

| 요소 | 의미 | 정본과 변경 규칙 | 검색 Context 노출 |
|---|---|---|---|
| `case_id` | immutable Case individual 하나의 고유 식별자 | Case revision마다 새로 발급하며 재사용하지 않음 | 항상 |
| `task_id` | 실제 요청·작업 instance인 Task individual 하나의 고유 식별자 | Task마다 하나이며 memory revision 식별자로 사용하지 않음 | provenance가 필요할 때 |
| `layer` | 해당 Case의 계층 위치 `L1...LN` | parent/child 및 Procedure expansion topology에서 계산한 파생값 | 항상 |
| `memory_kind` | Case가 L1 `tool_graph`인지 L2 이상 `procedure`인지 나타내는 의미 유형 | 자유 문자열이 아니라 ontology class와 SHACL 검증으로 결정 | 항상 |
| `ProblemFeatures` | 어떤 문제와 상황에서 만들어진 Case인지 설명하는 검색·의미 특성 | 의미가 바뀌면 새 Case revision 생성 | 항상 |
| `Situation` | 의도, 목표, 제약과 현재 상태를 묶은 ontology individual | Task용 의미 상황과 실행 시점 snapshot을 분리 | 항상 또는 참조 IRI |
| `solution` | Case가 기억하는 해결 구조의 참조 | L1은 ToolGraph, L2 이상은 Procedure | 항상 |
| `ToolGraph` | 실제 Tool node와 순서·조건·분기·병렬·loop edge | L1에서만 실행 기반으로 사용 | L1 Case에 전체 또는 budgeted slice |
| `Procedure` | 바로 아래 Layer Case 약 5~7개를 묶는 재사용 가능한 상위 절차 | L2...LN에서 사용하며 순서·조건·anchor 관계 보존 | L2 이상 Case에 전체 또는 budgeted slice |
| `OutcomeEvidence` | 특정 Case와 run에 대한 pending/success/failure 근거 | Case 본문과 분리된 append-only event | role과 근거를 함께 노출 |
| `provenance` | source, 작성자, compiler, reviewer, 시각과 integrity hash | 삭제·덮어쓰기 없이 추적 | 항상 요약, 필요 시 상세 |
| `review_state` | `draft/pending_review/active/deprecated/quarantined/retired` | outcome과 독립적인 governance 상태 | 항상 |
| `content_hash` | Case 내용과 relation snapshot의 무결성 digest | Case 생성 시 계산하고 이후 변경하지 않음 | version 정보에 포함 |
| `tool_registry_version` | ToolGraph node가 참조한 Tool schema snapshot | Tool drift 판정에 사용 | 호환성 정보에 포함 |
| `policy_version` | Case 생성·검토·검색에 적용된 policy snapshot | policy drift 판정에 사용 | governance 정보에 포함 |
| `embedding/index` | all-layer recall을 위한 파생 검색 view | ontology에서 언제든 재생성 가능하며 정본이 아님 | score와 build ID만 노출 |

### `case_id`

- `case_id`는 저장된 Case 한 개의 identity다.
- Case 내용을 in-place로 바꾸지 않는다. ToolGraph, Procedure, ProblemFeatures 또는 의미
  relation이 바뀌면 새 `case_id`를 발급하고 이전 Case와 `supersedes`로 연결한다.
- `case_id`는 Layer 전체에서 전역 고유해야 한다. L1 Case와 상위 Procedure Case가 같은
  ID를 공유하면 안 된다.
- 현재 코드의 UUID 문자열은 ontology IRI의 local identifier projection으로 볼 수
  있지만, RDF 정본에서는 Case IRI 자체가 identity다.

### `task_id`

- `task_id`는 실제 사용자 요청이나 실행 대상 Task 한 개의 identity다.
- 두 Task가 같은 질문과 Situation을 가져도 서로 다른 Task이면 `task_id`가 다르다.
- `task_id`는 Case revision 계보를 묶는 `family_id`나 `root_id` 역할을 하지 않는다.
- Case는 `derivedFromTask`, ExecutionRun은 `executesTask`, ContextBundle은
  `forTask` 관계로 Task를 참조한다.

### `layer`

- `layer`는 사용자가 입력하거나 영구 저장하는 권위 필드가 아니다.
- child expansion이 없는 L1 Case는 ToolGraph를 solution으로 가져야 한다.
- L2...LN Case는 Procedure이며, 바로 아래 Layer의 Procedure 또는 L1 ToolGraph
  Case를 ProcedureStep anchor로 참조한다.
- topology가 바뀌면 layer projection도 다시 계산한다.
- 검색 시 layer를 선필터로 사용하지 않고, all-layer recall 이후 결과 설명과
  structural expansion에 사용한다.

### `memory_kind`

정규 값은 두 가지다.

```text
tool_graph  # L1 전용: 실제 Tool node/edge를 가진 실행 기반
procedure   # L2...LN: 바로 아래 Layer Case 약 5~7개를 묶은 절차
```

다음 제약은 SHACL 또는 동등한 validator가 강제한다.

```text
layer == L1  ⇔ memory_kind == tool_graph
layer >= L2  ⇔ memory_kind == procedure
```

`memory_kind`는 검색 결과를 실행하라는 지시가 아니다. ReAct가 반환 구조를 올바르게
해석하고 필요한 하위 관계를 펼칠 수 있게 하는 type 정보다.

### `ProblemFeatures`

`ProblemFeatures`는 단순 embedding용 문장이 아니라 Case가 다루는 문제의 의미적
특성이다.

| 하위 요소 | 설명 | 정본 여부 |
|---|---|---|
| `request` | Case를 만들게 된 원 사용자 요청 또는 정규화 전 source 문장 | 원문 보존 |
| `intent` | 사용자가 무엇을 하려는지 | ontology relation/class로 정규화 |
| `goal` | 완료하려는 결과 | ontology relation/class로 정규화 |
| `category` | 넓은 domain 또는 업무 분류 | 보조 taxonomy |
| `keywords` | lexical recall을 위한 파생 검색어 | 재생성 가능한 파생값 |
| `constraints` | 반드시 지키거나 금지해야 하는 조건 | 의미적 정본 |
| `known_state` | 당시 확인된 Situation 사실 | provenance와 함께 저장 |
| `unknowns` | 확인되지 않은 값 | false와 구분하여 저장 |
| `context` | domain별 추가 정보 | schema와 provenance가 있는 값만 저장 |

ProblemFeatures가 비슷하다는 이유만으로 같은 Situation이나 같은 Case라고 단정하지
않는다. embedding은 seed를 찾고, ontology relation과 현재 RuntimeSituation이 그
Case를 다음 Tool 선택에 어떻게 참고할지 결정한다.

### 저장값, 파생값, 실행 시점 값의 구분

| 구분 | 예시 | 원칙 |
|---|---|---|
| 온톨로지 정본 | Case/Task/Situation IRI, `hasSolution`, `inSituation`, `supersedes`, provenance | mutation과 감사의 기준 |
| 파생 저장 view | `layer`, embedding, lexical text, graph feature, summary | 정본에서 재생성 가능해야 함 |
| evidence ledger | OutcomeEvidence, verdict, feedback, run link | Case 본문과 분리된 append-only 기록 |
| 실행 시점 상태 | RuntimeSituationSnapshot, ToolObservation, available Tools | Observation마다 갱신하고 필요 시 provenance로 연결 |
| Context 전용 값 | similarity score, retrieval rank, omission reason, bundle ID | Case 자체에 의미 정보처럼 역기록하지 않음 |

## 관계 사전

관계는 ontology object property로 정의한다. 아래 화살표는 항상
`주어 --관계--> 목적어` 방향이다. inverse 관계는 OWL로 선언할 수 있으므로 같은
사실을 양방향 triple로 중복 저장하지 않는다.

### 1. Case, Task와 Situation 관계

| 관계 | Domain → Range | 의미 | 주요 제약 |
|---|---|---|---|
| `inSituation` | Case → TaskSituation | 이 Case가 설명하는 의미적 상황 | Case revision당 정확히 1개 |
| `hasProblem` | Case → ProblemFeatures | Case가 해결하려는 문제의 구조화된 특성 | Case당 정확히 1개 |
| `derivedFromTask` | Case → Task | 실제 Task 또는 trace에서 이 Case가 컴파일됨 | 0개 이상, provenance 필수 |
| `executesTask` | ExecutionRun → Task | 이 run이 실제로 수행하는 Task | run당 정확히 1개 |
| `usedCase` | ExecutionRun → Case | Tool 선택에 참고한 Case | 0개 이상, 사용하지 않은 검색 결과는 별도 기록 |
| `forTask` | ContextBundle → Task | 이 Context Bundle의 대상 Task | bundle당 정확히 1개 |
| `forSituation` | ContextBundle → RuntimeSituationSnapshot | 검색에 사용한 현재 실행 상황 | bundle당 정확히 1개 |
| `withinTaskSituation` | RuntimeSituationSnapshot → TaskSituation | 실행 snapshot이 속한 의미적 상황 | 없거나 1개, 근거와 confidence 기록 |

`TaskSituation`은 재사용 Case의 의미적 범위를 나타내고,
`RuntimeSituationSnapshot`은 실제 ReAct run의 시점별 상태를 나타낸다. 두 개념을
하나의 mutable `context` 객체로 합치지 않는다.

### 2. Layer와 Procedure 확장 관계

| 관계 | Domain → Range | 의미 | 주요 제약 |
|---|---|---|---|
| `hasSolution` | Case → Procedure 또는 ToolGraph | Case가 기억하는 절차 구조 | Case당 정확히 1개 |
| `hasStep` | Procedure → ProcedureStep | 상위 Procedure를 이루는 단계 | 기본 5~7개 |
| `expandsTo` | ProcedureStep → Case | ProcedureStep을 구체화하는 하위 Case | 바로 아래 Layer로 연결 |
| `anchoredAt` | Case → ProcedureStep | 하위 Case가 어느 상위 step을 구체화하는지 표시 | `expandsTo`의 inverse |
| `dependsOn` | Case 또는 ProcedureStep → Case | 실행 전에 필요한 선행 Case | 방향성 있음, 근거 필수 |
| `hasNode` | ToolGraph → ToolNode | L1 ToolGraph의 실제 Tool node | 1개 이상 |
| `hasEdge` | ToolGraph → GraphEdge | L1 ToolGraph의 control-flow edge | 0개 이상 |
| `fromNode` | GraphEdge → ToolNode | edge 시작 node | 정확히 1개 |
| `toNode` | GraphEdge → ToolNode | edge 도착 node | 일반 edge는 정확히 1개 |
| `invokes` | ToolNode → Tool | node가 실제 호출하는 등록 Tool | 정확히 1개와 schema version |

`expandsTo`를 재귀적으로 따라가면 반드시 L1 ToolGraph Case에 도달해야 한다.
상위 Procedure의 cycle은 기본 금지하며, 반복은 L1 ToolGraph의 명시적인 bounded loop로
표현한다.

### 3. Revision과 대안 관계

| 관계 | 방향 | 의미 | HEAD 및 사용 규칙 |
|---|---|---|---|
| `supersedes` | 새 Case → 직전 Case | 같은 Situation에서 기존 절차를 수정·대체 | 새 Case가 검토·게시되면 HEAD 후보 |
| `revertOf` | 새 Case → 복원한 과거 Case | 과거 내용을 기반으로 새 revision 생성 | 현재 Case를 `supersedes`하면서 함께 기록 |
| `mergedFrom` | 새 Case → branch Case들 | 둘 이상의 branch를 검토 후 병합 | 최소 2개, 동일 Situation만 허용 |
| `alternativeTo` | Case ↔ Case | 둘 다 유효할 수 있으나 조건에 따라 선택되는 대안 | symmetric, HEAD 대체 의미 없음 |
| `conflictsWith` | Case ↔ Case | 동시에 채택할 수 없는 미해결 충돌 | symmetric, 자동 병합·실행 금지 |
| `relatedTo` | Case ↔ Case | 약한 참고 관계로 dependency나 revision 의미 없음 | symmetric, ranking 보조에만 사용 |

Revision 관계의 핵심 차이:

```text
case-B supersedes case-A
  # 같은 Situation에서 B가 A를 대체한다.

case-C supersedes case-B
case-C revertOf case-A
  # C는 현재 B를 대체하지만 내용은 과거 A를 복원했다.

case-M mergedFrom case-B1, case-B2
  # M은 같은 Situation의 두 branch를 병합했다.

case-X alternativeTo case-Y
  # X와 Y는 상황 조건에 따라 둘 다 유효할 수 있다.

case-P conflictsWith case-Q
  # P와 Q의 모순이 아직 해결되지 않았다.
```

제약:

- `supersedes`는 immediate predecessor 관계이며 transitive로 선언하지 않는다.
  전체 이력은 SPARQL property path `supersedes+`로 조회한다.
- 하나의 일반 revision은 `supersedes` 목적어가 최대 1개다. 다중 parent는
  `mergedFrom`으로 표현한다.
- `supersedes`, `revertOf`, `mergedFrom`으로 연결된 Case들은 같은
  `TaskSituation`을 가리켜야 한다.
- `alternativeTo`, `conflictsWith`, `relatedTo`는 symmetric이지만 transitive가
  아니다.
- `alternativeTo`를 `supersedes`처럼 사용해 이전 Case를 숨기면 안 된다.

### 4. Tool 실행과 Situation 전이 관계

| 관계 | Domain → Range | 의미 | 주요 제약 |
|---|---|---|---|
| `selectedUnder` | ToolInvocation → RuntimeSituationSnapshot | 어떤 상황에서 Tool을 선택했는지 | Tool 선택마다 필수 |
| `invokedTool` | ToolInvocation → Tool | 실제 호출한 Tool | 정확히 1개 |
| `producedObservation` | ToolInvocation → ToolObservation | Tool 호출이 만든 Observation | 정확히 1개, 실패도 포함 |
| `resultOf` | ToolObservation → ToolInvocation | Observation의 원 호출 | `producedObservation`의 inverse |
| `producedSituation` | ToolObservation → RuntimeSituationSnapshot | Observation 해석 후 만든 다음 상황 | 정확히 1개 |
| `nextSituation` | RuntimeSituationSnapshot → RuntimeSituationSnapshot | 같은 run에서 바로 다음 상태 | immediate transition, 덮어쓰기 금지 |

`nextSituation`도 immediate relation이다. 전체 상태 이력은 `nextSituation+`로
조회한다. Tool 실패와 부분 성공도 반드시 ToolObservation과 다음 Situation을
만든다.

### 5. Outcome, provenance와 governance 관계

| 관계 | Domain → Range | 의미 | 주요 제약 |
|---|---|---|---|
| `aboutCase` | OutcomeEvidence → Case | outcome 근거가 평가하는 정확한 Case | 정확히 1개 |
| `fromRun` | OutcomeEvidence → ExecutionRun | 근거가 나온 실제 run | 없거나 1개 |
| `supportedBy` | OutcomeEvidence → SourceArtifact | verdict를 뒷받침하는 문서·로그·서명 | 1개 이상 권장 |
| `derivedFromSource` | Case → SourceArtifact | Case를 컴파일한 원천 | 1개 이상 |
| `wasAttributedTo` | Case 또는 Evidence → Actor | 작성·판정 책임자 | role과 시각 필수 |
| `reviewedBy` | Case → Actor | Case revision 검토자 | active 게시 전에 필수 |
| `governedByPolicy` | Case/Run/Bundle → PolicySnapshot | 적용된 정책 snapshot | 정확한 version 고정 |
| `usesToolRegistry` | Case/Run → ToolRegistrySnapshot | 참조한 Tool schema snapshot | L1 Case와 run에 필수 |

OutcomeEvidence의 status와 review state는 object relation이 아니라 별도 상태
property다. `success`가 `active`를 뜻하지 않으며 `active`가 `success`를 뜻하지
않는다.

### 6. 검색과 Context Bundle 관계

| 관계 | Domain → Range | 의미 | 주요 제약 |
|---|---|---|---|
| `contains` | ContextBundle → Case/Procedure/ToolGraph/OutcomeEvidence | 모델에 실제 제공한 항목 | token budget 내 항목만 |
| `seededBy` | RetrievalTrace → Case | embedding·lexical recall로 직접 찾은 seed | 모든 Layer 허용 |
| `expandedFrom` | RetrievedItem → Case | ontology traversal을 시작한 seed Case | seed마다 1개 |
| `expansionPath` | RetrievedItem의 RDF list/data | seed에서 항목까지 거친 relation IRI 순서 | typed path 전체 보존 |
| `omittedItem` | ContextBundle → Case | 찾았지만 budget·governance 때문에 제외된 항목 | omission reason 필수 |
| `builtFromIndex` | ContextBundle → IndexBuild | 사용한 파생 index build | 정확히 1개 |

검색 score와 rank는 relation의 의미를 바꾸지 않는다. `seededBy` 1등 Case도
`supersedes`, `inSituation`, Procedure expansion과 OutcomeEvidence를 함께 보지 않고
실행 지시로 취급해서는 안 된다.

## INV-003 — 콘텐츠, 근거, 호환성, 인덱스 버전을 분리한다

Chaeshin의 “버전”은 하나의 증가 숫자가 아니다. 최소한 다음 버전 축을 서로
독립적으로 기록한다.

| 버전 축 | 의미 | 변경되는 경우 |
|---|---|---|
| `case_id` | 하나의 변경 불가능한 Case 메모리를 가리키는 고유 식별자 | 최초 생성과 모든 revision 생성 시 각각 새로 발급 |
| `inSituation` | Case가 속한 `TaskSituation` individual을 가리키는 ontology relation | Case 생성 시 연결하며 상황 변경은 새 Situation으로 표현 |
| `supersedes` | 같은 Situation에서 현재 Case가 대체하는 직전 Case를 가리키는 relation | revise 또는 revert 시 하나만 연결 |
| `mergedFrom` | 같은 Situation에서 병합한 두 개 이상의 branch Case를 가리키는 relation | merge 시에만 연결 |
| `content_hash` | 해당 Case의 ProblemFeatures, ToolGraph/Procedure 구조와 anchor의 무결성 digest | Case 내용이 달라지면 새로운 `case_id`와 함께 새로 계산 |
| `evidence_seq` | 실행 결과, 사용자 판정, 평가 근거의 append-only 순서 | 해당 revision에 새 outcome 근거가 들어올 때 증가 |
| `tool_registry_version` | L1 node가 참조한 Tool과 입력·출력 schema snapshot | Tool 등록부나 schema가 변경될 때 갱신 |
| `policy_version` | 저장·검색·실행 당시 적용한 권한 및 정책 snapshot | 조직 정책 또는 권한 규칙이 변경될 때 갱신 |
| `index_build_id` | embedding, lexical, graph index와 요약 view의 파생 버전 | 재색인 또는 검색 모델 변경 시 생성 |
| `bundle_snapshot_id` | 한 번의 검색에서 사용한 memory/index/policy 조합 | ReAct에 Context를 주입할 때마다 생성 |

버전 불변식:

- `case_id`는 Case individual 하나만 식별한다. 서로 다른 Case나 revision이 같은
  `case_id`를 공유하면 안 된다.
- revision은 기존 Case를 수정하는 작업이 아니라, 새 `case_id`를 가진 immutable
  Case를 만들고 ontology의 `supersedes` relation으로 직전 Case를 연결하는 작업이다.
- `supersedes`로 연결되는 두 Case는 같은 `TaskSituation` individual을 `inSituation`으로
  가리켜야 한다. intent, goal, hard constraint 또는 domain이 달라져 Situation이
  바뀌면 그것은 revision이 아니라 별도의 Case 또는 명시적인 `alternativeTo`
  관계다.
- 실제 작업은 고유 `task_id`, 실행 1회는 `run_id`로 식별하며, 실행이 어떤
  `case_id`들을 참고했는지 별도 relation으로 기록한다.
- 현재 버전인 `HEAD`는 mutable한 Case 본문이 아니라 immutable `case_id`를 가리키는
  ref 또는 동일한 의미의 current-state projection이다.
- 같은 상황 안에서 L1의 node·edge·condition·parameter 의미, L2 이상의 Procedure
  구성·anchor·하위 참조 또는 비상황 메타데이터가 바뀌면 새 Case revision을 만든다.
- 상위 Procedure Case는 하위 memory의 정확한 `case_id`를 참조한다.
  하위 `HEAD`가 바뀌었다고 과거 상위 Procedure의 의미가 조용히 바뀌면 안 된다.
- outcome과 verdict는 정확한 `case_id`, 실행 run, 당시 state, Tool registry와
  policy snapshot에 결속된 evidence event다. 과거 revision의 success를 새 revision에
  자동 승계하지 않는다.
- 재색인, embedding 모델 교체 또는 summary 재생성은 파생 view 변경이다. 메모리
  의미가 같다면 새 Case revision을 만들지 않는다.
- rollback은 ref를 과거로 되감거나 history를 지우는 작업이 아니다. 과거 내용을
  복원한 **새 Case revision**을 만들고, 새 Case에서 현재 Case로 `supersedes`, 새
  Case에서 복원 근거인 과거 Case로 `revertOf` relation을 연결한다.
- 동시에 유효한 지역·상태·정책 변형은 각각 새 `case_id`를 가진 branch로 보존한다.
  두 branch는 같은 Case를 `supersedes`로 가리킬 수 있지만 서로의 `case_id`를
  공유하지 않는다. 병합은 동일한 Situation 안에서만 semantic three-way merge와
  충돌 검토를 거치며, merge 결과에도 새 `case_id`를 발급하고 branch Case들을
  `mergedFrom`으로 연결한다.
- 하나의 변경이 여러 Procedure와 anchor에 영향을 주면 관련 revision과 relation을
  원자적으로 게시한다. 검색은 부분 반영된 계층을 관찰해서는 안 된다.
- 모든 Context Bundle은 검색한 case ID, 대상 task ID, evidence sequence, index build, Tool
  registry, policy version과 state fingerprint를 기록해야 재현할 수 있다.

권장 식별 예시는 다음과 같다.

```text
case-01 -inSituation-> situation-kimchi-standard
case-02 -inSituation-> situation-kimchi-standard
case-02 -supersedes---> case-01
case-03 -inSituation-> situation-kimchi-standard
case-03 -supersedes---> case-02
HEAD -----------------> case-03

task_id: task-2026-08-30-001  # 이번 사용자 작업
evidence_seq: case-03/e12
tool_registry: tools-2026-08-30.3
policy: kitchen-policy-4
index_build: idx-91
bundle_snapshot: ctx-01K...
run_id: run-01K...  # 실제 실행이 있었을 때만
```

금지되는 해석:

- 같은 `case_id`의 내용을 in-place로 바꾸거나 두 revision에서 공유하는 것
- 공통 `root_case_id` 또는 `family_id`를 revision 식별자로 다시 도입하는 것
- Situation이 다른 두 Case를 `supersedes`로 연결하는 것
- feedback 또는 outcome 추가를 ToolGraph 수정과 같은 버전으로 취급하는 것
- 과거 성공 판정을 수정된 graph에 자동 복사하는 것
- 재색인만으로 새 Case revision을 만드는 것
- rollback 과정에서 실패 revision과 감사 이력을 삭제하는 것

## INV-004 — 저장, 판정, 게시, 검색 권한을 분리한다

Chaeshin의 거버넌스는 “누가 무엇을 제안하고, 검증하고, 판정하고, 검색 가능하게
만드는가”를 명시적으로 분리한다.

| 역할 | 할 수 있는 일 | 단독으로 할 수 없는 일 |
|---|---|---|
| Contributor / Host ReAct | 실제 trace, SOP 또는 수정 후보 제출 | 후보를 곧바로 승인된 memory나 success로 확정 |
| Memory Compiler | source를 L1 ToolGraph와 L2...LN Procedure 후보로 컴파일하고 provenance 부착 | source에 없는 Tool·edge·조건을 근거 없이 권위화 |
| Validator | schema, graph, anchor, Tool compatibility, 정책과 보안 규칙 검사 | 업무 결과의 성공·실패 판정 |
| Reviewer / Publisher | 검토된 immutable Case를 active HEAD로 게시 | 과거 Case와 audit event 삭제 |
| Outcome Authority | 특정 Case revision과 run에 success/failure verdict 서명 | 다른 Case revision으로 verdict 자동 전파 |
| Retriever | ACL·tenant·상태·버전 정책을 통과한 모든 Layer를 함께 검색 | 검색 순위만으로 Tool 실행 또는 plan 확정 |
| Host ReAct | 반환된 Context를 참고해 다음 Tool 하나를 선택 | 메모리의 저장·승인·판정 권한을 암묵적으로 획득 |

### 수명주기 상태

콘텐츠 검토 상태와 실행 outcome 상태는 서로 다른 축이다.

```text
review_state: draft → pending_review → active → deprecated | quarantined | retired
outcome.status: pending | success | failure
```

- 새로 컴파일하거나 Agent가 retain한 memory는 기본적으로 `draft` 또는
  `pending_review`이며, outcome은 `pending`이다.
- `active`는 검색 게시 승인을 뜻하며 success를 뜻하지 않는다. 반대로 과거에
  success였더라도 Tool 또는 정책 변화로 `quarantined`될 수 있다.
- `deprecated`, `quarantined`, `retired` revision은 일반 검색 결과에서 기본 제외한다.
  감사 또는 `as_of` 조회처럼 명시된 경로에서만 provenance와 함께 읽는다.
- “모든 Layer를 함께 검색”한다는 INV-002는 **검색 권한과 게시 정책을 통과한 모든
  Layer**를 뜻한다. ACL, tenant 격리, quarantine을 우회한다는 뜻이 아니다.
- hard governance filter는 저장소가 검색 전에 결정적으로 적용한다. 이것은 ReAct
  앞에 `applicable / conditional / inapplicable` 분류 단계를 추가하는 것이 아니다.

### Provenance와 감사

모든 memory revision과 evidence event는 최소한 다음을 보존한다.

- source type과 immutable source reference/hash
- 생성자, compiler, reviewer, outcome authority의 식별자와 역할
- 생성·검토·게시·판정 시각
- 변경 이유, semantic diff, parent revision 또는 merge parents
- Tool registry, policy, tenant, sensitivity와 retention scope
- 서명 또는 검증 가능한 integrity digest

감사 로그는 append-only이며 retain, revise, branch, merge, publish, verdict, reindex,
retrieve, quarantine, tombstone과 purge를 구분해 기록한다.

### 변경 영향과 안전

- L1 Tool schema가 바뀌면 그 Tool을 참조하는 L1 revision과 이를 포함하는 상위
  Procedure의 transitive dependency를 검사한다.
- node가 삭제되거나 의미가 바뀌면 해당 node에 걸린 child anchor를 찾아
  `stale` 또는 `needs_review`로 전환한다. child를 조용히 삭제하거나 재연결하지
  않는다.
- policy drift는 과거 outcome을 지우지 않지만 현재 검색·사용 가능성 projection을
  바꿀 수 있다.
- memory source 안의 명령문은 실행 명령이 아니라 untrusted evidence로 취급한다.
  prompt injection, provenance 누락, cross-tenant source는 검역한다.
- 삭제 요청은 검색 차단용 tombstone, 파생 index purge, 법적 감사 보존과 실제 원본
  삭제 정책을 구분해 처리한다.
- 권한 없는 actor는 publish, verdict, merge, revert, quarantine 해제를 수행할 수
  없다. 모든 mutation은 optimistic concurrency 또는 동등한 충돌 검사를 거친다.

금지되는 해석:

- Agent가 실행을 마쳤다는 이유만으로 success 판정
- 출처와 검토자 없는 memory를 active로 자동 게시
- tenant 또는 민감도 필터를 ranking 점수에만 맡기는 것
- Tool·정책 drift 이후에도 과거 success graph를 현재 유효하다고 간주
- 관리자가 history를 남기지 않고 graph, verdict 또는 revision 삭제

## INV-005 — 정본 메모리 모델은 온톨로지다

Chaeshin의 Case, Task, Situation, Procedure, ToolGraph, revision, outcome과 governance는 서로
독립된 테이블 row나 중첩 JSON만으로 정의하지 않는다. **온톨로지의 class,
individual, property와 constraint가 의미의 정본**이며, SQLite 문서, embedding과
검색 index는 그 정본에서 만든 projection이다.

이 모델에서는 공통 `family_id`가 필요하지 않다.

- 각 Case는 서로 다른 IRI와 `case_id`, 각 Task는 서로 다른 IRI와 `task_id`를 가진
  individual이다.
- 같은 상황이라는 사실은 ID 공유가 아니라 두 Case가 동일한 `TaskSituation`
  individual을 `inSituation` 관계로 가리켜 표현한다.
- 같은 상황에서 이전 절차를 고친 경우에만 새 Case가 이전 Case를 `supersedes`한다.
- 상황이 다르면 별도 Case이며 `alternativeTo`, `relatedTo` 같은 관계는 가질 수
  있어도 revision 관계로 연결하지 않는다.
- L1 Case의 solution은 `ToolGraph` individual이고, L2...LN Case의 solution은 바로
  아래 Layer Case 약 5~7개를 묶는 `Procedure` individual이다.

### TBox — 개념과 관계의 정의

최소 class 집합:

```text
ChaeshinEntity
├─ Case
├─ Task
├─ ProblemFeatures
├─ Situation
│  ├─ TaskSituation             # Case revision들이 공유하는 의미적 상황
│  └─ RuntimeSituationSnapshot  # Observation마다 갱신되는 실행 시점 상태
├─ SituationClaim               # 현재 상태에 대한 true/false/unknown 주장
├─ StatePredicate               # 상태 주장이 가리키는 의미적 술어
├─ Procedure             # L2...LN
├─ ProcedureStep
├─ ToolGraph             # L1
├─ ToolNode
├─ GraphEdge
├─ Tool
├─ ExecutionRun
├─ ToolInvocation
├─ ToolObservation
├─ ObservationEvidence           # 검증·정규화된 관측 근거
├─ ExpectedEffect                # Tool 이후 예상되는 정성적 상태 변화
├─ ObjectivePreference           # 목표 달성도·비용·위험·시간 선호
├─ OutcomeEvidence
├─ ContextBundle
├─ RetrievalTrace
├─ RetrievedItem
├─ SourceArtifact
├─ Actor
├─ IndexBuild
├─ ToolRegistrySnapshot
└─ PolicySnapshot
```

최소 object property 집합:

```text
Case       -inSituation-------> TaskSituation
Case       -hasProblem-------> ProblemFeatures
Case       -hasSolution-------> Procedure | ToolGraph
Case       -supersedes--------> Case
Case       -revertOf----------> Case
Case       -mergedFrom--------> Case
Case       -alternativeTo-----> Case
Case       -conflictsWith-----> Case
Case       -relatedTo---------> Case
Case       -derivedFromTask---> Task
Case       -derivedFromSource-> SourceArtifact
Case       -reviewedBy--------> Actor
Case       -governedByPolicy--> PolicySnapshot
Case       -usesToolRegistry--> ToolRegistrySnapshot
Procedure  -hasStep-----------> ProcedureStep
ProcedureStep -expandsTo------> Case
Case       -anchoredAt--------> ProcedureStep
Case       -dependsOn---------> Case
ToolGraph  -hasNode-----------> ToolNode
ToolGraph  -hasEdge-----------> GraphEdge
GraphEdge  -fromNode----------> ToolNode
GraphEdge  -toNode------------> ToolNode
ToolNode   -invokes-----------> Tool
ExecutionRun -executesTask----> Task
ExecutionRun -usedCase--------> Case
ToolInvocation -selectedUnder-> RuntimeSituationSnapshot
ToolInvocation -invokedTool---> Tool
ToolInvocation -producedObservation-> ToolObservation
ToolObservation -resultOf-----> ToolInvocation
ToolObservation -producedSituation-> RuntimeSituationSnapshot
ToolObservation -supportsClaim-> SituationClaim
ObservationEvidence -derivedFromObservation-> ToolObservation
ObservationEvidence -supportsClaim-> SituationClaim
RuntimeSituationSnapshot -nextSituation-> RuntimeSituationSnapshot
RuntimeSituationSnapshot -withinTaskSituation-> TaskSituation
RuntimeSituationSnapshot -hasClaim-> SituationClaim
SituationClaim -aboutPredicate-> StatePredicate
Tool       -hasExpectedEffect-> ExpectedEffect
ExpectedEffect -aboutPredicate-> StatePredicate
ExpectedEffect -mayTransitionTo-> SituationClaim
Task       -hasPreference-----> ObjectivePreference
OutcomeEvidence -aboutCase----> Case
OutcomeEvidence -fromRun------> ExecutionRun
OutcomeEvidence -supportedBy--> SourceArtifact
OutcomeEvidence -wasAttributedTo-> Actor
ContextBundle -forTask--------> Task
ContextBundle -forSituation---> RuntimeSituationSnapshot
ContextBundle -contains-------> Case | Procedure | ToolGraph | OutcomeEvidence | SituationClaim | ObservationEvidence | ExpectedEffect | ObjectivePreference
RetrievalTrace -seededBy------> Case
RetrievedItem -expandedFrom---> Case
ContextBundle -omittedItem----> Case
ContextBundle -builtFromIndex-> IndexBuild
```

주요 data property에는 `case_id`, `task_id`, `memory_kind`, `layer`, `content_hash`, `review_state`,
`outcome.status`, `truth_status`, `confidence`, `freshness`, `horizon`, `urgency`,
생성 시각, provenance hash와 version digest가 포함된다. `layer`는
저장된 진실이라기보다 Procedure expansion topology에서 계산한 projection이어야 한다.

### ABox — 실제 Case, Task와 Situation

김치찌개 예시는 다음처럼 표현한다.

```turtle
:situation-kimchi-standard a :TaskSituation ;
    :intent "recipe_explanation" ;
    :goal "김치찌개 조리법 설명" .

:task-current a :Task ;
    :taskId "task-current" .

:case-01 a :Case ;
    :caseId "case-01" ;
    :inSituation :situation-kimchi-standard ;
    :hasSolution :kimchi-procedure-r1 .

:case-02 a :Case ;
    :caseId "case-02" ;
    :inSituation :situation-kimchi-standard ;
    :supersedes :case-01 ;
    :derivedFromTask :task-current ;
    :hasSolution :kimchi-procedure-r2 .

:kimchi-procedure-r2 a :Procedure ;
    :hasStep :cook-kimchi-step .

:cook-kimchi-step a :ProcedureStep ;
    :expandsTo :case-kimchi-l1-r2 .

:case-kimchi-l1-r2 a :Case ;
    :caseId "case-kimchi-l1-r2" ;
    :inSituation :situation-kimchi-standard ;
    :anchoredAt :cook-kimchi-step ;
    :hasSolution :kimchi-tool-graph-r2 .

:kimchi-tool-graph-r2 a :ToolGraph ;
    :layer 1 ;
    :hasNode :prepare-kimchi, :boil-stew, :taste-stew .
```

`case-01`과 `case-02`는 `case_id`를 공유하지 않는다. 둘이 같은 상황이라는 사실은
`:inSituation :situation-kimchi-standard`로 표현된다. `task-current`는 이 Case들과
다른 종류의 individual이며 실제 사용자 작업을 가리킨다.

동일한 정보를 LLM Context에 넣을 때에는 POMDP 수식을 강제하지 않고 다음처럼
읽을 수 있는 텍스트 projection으로 직렬화할 수 있다.

```yaml
runtime_situation: situation-kimchi-t0
state_claims:
  - predicate: user.intent
    value: recipe_explanation
    truth_status: true
    source: user_prompt
  - predicate: servings
    truth_status: unknown
available_actions:
  - answer_recipe
  - ask_servings
retrieved_memory:
  procedures: [case-02]
  tool_graphs: [case-kimchi-l1-r2]
expected_effects:
  ask_servings: "servings unknown을 해소할 수 있음"
observation_evidence: []
objective_preferences:
  risk: low
  horizon: immediate
```

이 projection은 ontology individual과 property에서 생성하는 파생 표현이다. Vector
DB에는 이 텍스트 또는 필드별 embedding을 저장할 수 있지만, claim과 provenance의
정본은 ontology에 남는다.

### RDF, OWL, SHACL, SWRL, SPARQL의 책임

| 기술 | Chaeshin에서의 책임 |
|---|---|
| RDF | Case, Task, Procedure, ToolGraph, Situation과 관계를 triple로 표현 |
| RDFS/OWL | class 계층, domain/range, disjoint class, relation 의미와 추론 정의 |
| SHACL | L1은 ToolGraph여야 함, Case/Task ID 유일성, memory kind, graph endpoint와 revision 상황 일치 등을 폐쇄형으로 검증 |
| SWRL | 명시적 triple로부터 stale 영향, Procedure dependency, 경고 후보 같은 파생 관계를 추론할 때 제한적으로 사용 |
| SPARQL | 모든 Layer seed 조회, parent/child·dependency·revision·outcome 구조 확장과 감사 질의 |

OWL 또는 SWRL 추론 결과만으로 mutation을 승인하지 않는다. 유일성, 필수 필드,
동일 상황 revision, Tool schema와 governance 위반처럼 저장을 거부해야 하는 규칙은
SHACL 또는 동등한 deterministic validator가 집행한다.

예를 들어 `supersedes` 관계는 다음 의미를 만족해야 한다.

```text
case-B supersedes case-A
  ⇒ case-A != case-B
  ∧ case-A.inSituation == case-B.inSituation
  ∧ case-A.review_state is not deleted
  ∧ case-B has a new immutable case_id
```

### 온톨로지 검색과 embedding 검색의 결합

온톨로지를 사용해도 embedding 검색을 없애지 않는다. 구현은 vector 기능이 있는
graph store 하나를 사용할 수도 있고 ontology store와 Vector DB를 분리할 수도
있다. 어느 경우에도 ontology revision이 정본이고 vector/lexical index는 다시 만들
수 있는 파생 projection이다. 상세 단계는 `INV-002`의 정규 검색 파이프라인을
따른다.

```text
User query + RuntimeSituationSnapshot
  → 모든 Layer의 L1 ToolGraph/L2+ Procedure Case를 vector + lexical recall
  → seed ontology individuals
  → SPARQL/property-path로 expansion, prerequisite, alternative, revision, outcome 확장
  → Situation·Tool·정책·validity 기반 filter/rerank
  → governance/SHACL validation과 budget packing을 통과한 ContextBundle
  → ReAct가 참고하여 다음 Tool 하나를 직접 선택
```

- embedding은 표현이 비슷한 seed를 찾는다.
- ontology relation은 질문에 직접 등장하지 않은 하위 ToolGraph, 선행 Procedure,
  같은 Situation의 Case revision과 outcome 근거를 찾는다.
- 검색 index는 ontology의 모든 검색 가능 Layer를 포함해야 한다.
- graph store와 vector index가 불일치하면 ontology revision을 기준으로 파생 index를
  다시 만들며, 오래된 index 결과를 Context에 넣지 않는다.

금지되는 해석:

- ontology를 embedding 대신 쓰는 단순 keyword taxonomy로 축소
- JSON 안의 `layer`, `parent_id`, `status`를 온톨로지보다 더 권위 있는 정본으로 취급
- 서로 다른 Situation의 Case를 `supersedes`로 연결
- OWL의 open-world 추론만으로 필수 필드와 거버넌스 검증이 끝났다고 간주
- 모든 Layer를 검색한다면서 특정 class나 Layer의 embedding만 생성

## INV-006 — Tool 선택은 Situation에 조건화되고 매 Observation 뒤 갱신된다

Tool 선택은 사용자 query만의 함수가 아니다. 동일한 query와 동일한 검색 결과를
받아도 현재 Situation, 사용 가능한 Tool, 권한과 직전 Observation이 다르면 다음
Tool이 달라질 수 있다.

```text
Action_t = ReAct(
  UserQuery,
  Situation_t,
  ChaeshinContext_t,
  AvailableTools_t,
  Observations_{<t}
)
```

- ReAct는 `Situation_t`와 Chaeshin 검색 결과를 참고해 다음 Tool 하나를 직접
  선택한다.
- 검색된 ToolGraph의 다음 node나 similarity 1등 Tool을 기계적으로 실행하지 않는다.
- 안전 조건, 권한, 가용 자원, 앞선 Tool의 성공·실패와 출력값은 모두 현재
  Situation의 일부다.
- 모르는 값은 false로 간주하지 않고 unknown으로 유지한다.
- 별도 Planner나 `applicable / conditional / inapplicable` 분류 단계를 추가하지
  않는다.

### POMDP-inspired 해석 — 정형 solver 요구사항이 아님

Chaeshin은 부분적으로 관측된 환경을 다루므로 POMDP의 구성 요소를 **텍스트와
온톨로지로 표현하는 해석 틀**로 사용할 수 있다. 그러나 전이·관측 확률을 반드시
수치로 학습하거나, 최적 policy를 계산하는 POMDP solver를 Chaeshin 내부에 두지는
않는다.

| POMDP 요소 | Chaeshin에서의 텍스트·온톨로지 표현 | 필수 정형화 수준 |
|---|---|---|
| `S` State | 실제 환경 상태는 직접 확정하지 않는다. `RuntimeSituationSnapshot`이 지금까지 확인된 `SituationClaim`과 unknown을 가진 lightweight belief state 역할을 한다. | `true / false / unknown`, 근거와 freshness는 필수. 완전한 상태 열거는 불필요 |
| `A` Action | 현재 ReAct가 선택할 수 있는 Tool과 그 입력 후보. L1 ToolGraph의 ToolNode는 과거 Action 구조에 대한 근거다. | Tool registry identity와 현재 가용성 필요 |
| `O` Observation | Tool 실행 결과인 `ToolObservation` 또는 이를 정제한 `ObservationEvidence`. | source Tool, schema validation, 시각, provenance 필요 |
| `T` Transition | Tool 실행 뒤 예상되는 상태 변화를 `ExpectedEffect`, `mayTransitionTo`, guard 같은 정성적 hint로 표현한다. | 확률값은 선택 사항이며 실제 Observation보다 권위가 낮음 |
| `R` Reward | `ObjectivePreference`의 목표 달성도, 비용, 위험, 지연 선호로 표현한다. | 사용자 verdict 및 `OutcomeEvidence`와 분리해야 함 |
| `Z` Observation likelihood | Observation의 신뢰도, 출처 신뢰성, schema 적합성, freshness로 관측 품질을 표현한다. | 수치 확률은 선택 사항. 근거 없는 confidence는 금지 |
| `γ (gamma)` Discount | `horizon`, `urgency`, `latency_budget`처럼 장·단기 선호를 나타낸다. | 전역 고정 할인율은 필수가 아니며 task별 텍스트 값도 허용 |

핵심 구분은 다음과 같다.

```text
실제 Environment State
  != RuntimeSituationSnapshot
  = 지금까지의 Observation으로 지지되는 state claim과 unknown의 집합

ToolGraph
  != 현재 실행할 고정 policy
  = 과거에 사용된 Action 구조에 대한 절차 근거

OutcomeEvidence
  != 즉시 Reward 숫자
  = 특정 Case revision과 run에 연결된 결과·사용자 판정 근거
```

따라서 Chaeshin의 역할은 현재 belief를 이용해 policy를 계산하는 것이 아니라,
ReAct가 다음 Tool을 고를 때 필요한 다음 정보를 Context로 공급하는 데까지다.

```text
Current Situation claims and unknowns
+ available Tools
+ retrieved Procedures and L1 ToolGraphs
+ expected effects, past observations and outcomes
+ risk, cost, horizon and missing-observation hints
  -> bounded Chaeshin Context
  -> ReAct가 다음 Tool 하나를 직접 선택
```

`ExpectedEffect`는 현재 상태를 바꾸는 명령이 아니다. 실제 Tool Observation이
도착하고 schema, provenance, freshness 검증을 통과해야만 새로운
`SituationClaim`의 근거가 될 수 있다.

### Observation 이후의 Situation 재구성

모든 Tool 호출은 성공 여부와 관계없이 Observation을 만든다. ReAct는 다음 Tool을
선택하기 전에 Observation을 해석해 새로운 Situation을 구성해야 한다.

```text
Situation_t
  → ReAct가 Tool_t 선택
  → Tool_t 실행
  → Observation_t
  → Situation_{t+1} 재구성
  → 필요하면 Chaeshin all-layer 재검색
  → ReAct가 Tool_{t+1} 선택
```

`Situation_{t+1}`에는 최소한 다음 변화가 반영되어야 한다.

- 새로 확인된 사실과 아직 확인되지 않은 unknown
- Tool output으로 생성·수정·삭제된 artifact 또는 resource
- Tool 성공, 부분 성공, 실패와 오류 유형
- 바뀐 권한, 가용 Tool, 자원, 시간 및 안전 조건
- 사용자가 중간에 수정한 목표와 hard constraint
- 이전 Situation과 달라진 field 및 state revision

Tool output은 곧바로 Situation의 참값이 아니다. schema validation, Tool provenance,
오류와 freshness를 확인한 Observation만 현재 Situation 근거로 사용한다.

### 재검색 조건

Situation은 매 Observation 뒤 항상 갱신하지만, Chaeshin을 매번 다시 검색할 필요는
없다. 다음 Tool 후보나 필요한 Procedure/ToolGraph 구조가 달라질 수 있을 때만 최신
Situation으로 모든 Layer를 다시 검색한다.

- 기존 선례가 전제로 삼은 상태와 충돌하는 사실이 확인됨
- Tool 실패로 alternative Procedure 또는 다른 ToolGraph가 필요함
- 안전, 권한, 자원 또는 hard constraint가 바뀜
- 사용자의 목표나 의도가 바뀜
- 현재 Context에 필요한 branch, Procedure 또는 Tool이 없음

재검색하지 않더라도 다음 Tool 선택은 반드시 최신 `Situation_{t+1}`을 기준으로
한다. “재검색하지 않음”은 “상황을 다시 파악하지 않음”을 의미하지 않는다.

### 온톨로지 표현

각 시점의 `RuntimeSituationSnapshot`은 덮어쓰는 JSON 상태가 아니라 별도의
ontology individual로 표현해 실행 중 상태 전이를 재현할 수 있어야 한다.

```text
situation-t0 -nextSituation--------> situation-t1
observation-01 -producedSituation--> situation-t1
observation-01 -resultOf-----------> tool-run-01
tool-run-01 -selectedUnder---------> situation-t0
tool-run-01 -invokedTool-----------> tool-A
```

이 관계를 통해 “어떤 상황에서 왜 Tool A를 선택했고, 그 결과 상황이 어떻게
바뀌어 다음 Tool B를 선택했는가”를 추적할 수 있다. 지속 메모리에 저장할 때에는
실제 실행 trace와 관련 Situation snapshot을 provenance로 연결하되, ReAct의 숨은
장문 사고를 저장 대상으로 삼지 않는다.

금지되는 해석:

- query가 같으면 항상 같은 Tool 선택
- 첫 검색에서 가져온 ToolGraph 전체를 고정 plan으로 실행
- Tool 성공 응답만 기록하고 실패·부분 성공을 Situation에서 누락
- Tool output을 검증 없이 사실로 확정
- Observation 뒤 Situation을 갱신하지 않고 이전 상태로 다음 Tool 선택
- Situation이 바뀌었는데도 필요한 graph가 Context에 없다는 사실을 무시

## Chaeshin 검색 결과의 활용

Chaeshin의 출력은 실행 명령이나 완성된 plan이 아니라 ReAct가 다음 Tool을 고를 때
참고하는 memory context다. ReAct 앞에 별도의 Planner나
`applicable / conditional / inapplicable` 분류 단계를 두지 않는다.

```text
MemoryObservation
  = ProblemFeatures
  + retrieved L1 ToolGraphs and L2...LN Procedures
  + ToolGraph/Procedure relations
  + Situation claims, unknowns and ObservationEvidence
  + expected effects and ObjectivePreferences
  + outcomes and provenance

MemoryObservation + current Observation + available Tools
  → ReAct가 다음 Action/Tool 하나를 직접 선택
```

## Required verification

아키텍처 관련 변경은 최소한 다음을 검증해야 한다.

1. L1 fixture가 여러 Tool node를 가진 ToolGraph로 저장되고 손실 없이 반환된다.
2. L2 이상의 fixture가 바로 아래 Layer Procedure 또는 L1 ToolGraph 참조를
   보존하며 기본 5~7개 step 구성을 검증한다.
3. 하나의 query에서 L1, L2, LN fixture가 모두 동일 retrieval 후보군에 들어간다.
4. Layer 제한 인자를 주지 않아도 all-layer retrieval이 기본 동작한다.
5. 논문의 영문·국문 본문과 Draw.io 그림이 같은 Layer 의미를 사용한다.
6. ReAct prompt가 검색 결과를 참고해 바로 다음 Tool을 선택하며, 별도 Planner나
   후보 분류 단계를 요구하지 않는다.
7. 같은 Situation에서 ToolGraph/Procedure의 의미가 바뀌면 새 `case_id`를 가진 immutable
   Case를 만들고 `supersedes` relation으로 과거 Case를 연결하며, 과거 내용을
   그대로 재생할 수 있다.
8. outcome event 추가와 index rebuild가 새 Case revision을 만들지 않는다.
9. 새 revision은 과거 revision의 success/failure verdict를 자동 상속하지 않는다.
10. Tool 또는 정책 변경 시 영향을 받는 L1과 상위 Procedure가 함께 탐지된다.
11. 권한 없는 actor의 publish/verdict/merge/revert 요청이 거부되고 audit event가
    남는다.
12. active이며 ACL·tenant 정책을 통과한 L1...LN만 all-layer recall 후보가 된다.
13. `supersedes`로 연결된 모든 Case는 같은 Situation individual을 `inSituation`으로
    가리키며, Situation이 다른 Case의 revision 연결은 거부된다.
14. Case, Task와 Situation이 서로 다른 ontology individual로 저장되고, 실제
    작업과 재사용 메모리의 ID가 섞이지 않는다.
15. SHACL 검증에서 L1의 ToolGraph type, 고유 Case/Task ID, memory kind, graph
    endpoint와 동일 상황 revision 제약이 강제된다.
16. embedding recall이 모든 검색 가능한 Layer를 포함하고, seed 결과가 ontology
    relation을 따라 확장된다.
17. 동일 query fixture라도 Situation이 다르면 기대되는 다음 Tool이 달라진다.
18. 모든 Tool Observation 뒤 새로운 Situation snapshot이 생성되고 다음 Tool
    선택이 최신 snapshot을 참조한다.
19. Situation 변화가 retrieval 결과 또는 필요한 graph 구조를 바꾸는 fixture에서는
    최신 Situation으로 all-layer 재검색이 수행된다.
20. Tool output의 schema, provenance 또는 freshness 검증이 실패하면 해당 값을
    Situation의 확정 사실로 승격하지 않는다.
21. SHACL이 각 relation의 domain, range, cardinality와 동일 Situation 제약을
    검증하고 잘못된 `supersedes`, `expandsTo`, `aboutCase` 연결을 거부한다.
22. `supersedes`, `revertOf`, `mergedFrom`, `alternativeTo`, `conflictsWith`가 서로
    다른 의미로 직렬화되며 revision 조회에서 혼합되지 않는다.
23. 실제 환경 State와 `RuntimeSituationSnapshot`을 동일시하지 않으며, unknown
    상태가 false로 강제 변환되지 않는다.
24. `ExpectedEffect`만으로 Situation을 변경하지 않고, 검증된 Tool Observation이
    새로운 `SituationClaim`을 지지할 때만 다음 snapshot에 반영한다.
25. `ObjectivePreference`, 사용자 verdict와 `OutcomeEvidence`를 하나의 Reward
    값으로 합쳐 저장하지 않는다.
26. POMDP-inspired 표현을 사용하더라도 Chaeshin에 별도 policy solver, Planner
    또는 자동 graph executor가 추가되지 않는다.
27. 검색 query fixture가 사용자 질문뿐 아니라 최신 Situation claim, unknown, 목표와
    hard constraint를 포함해 재현 가능한 `QueryProfile`과 embedding을 만든다.
28. Vector/lexical seed가 `expandsTo`, `dependsOn`, `alternativeTo`, revision과 outcome
    관계를 따라 확장되고, 필요한 ontology closure가 누락되지 않는다.
29. Situation·Tool·정책이 다른 fixture에서 동일 vector seed의 재정렬 결과가 달라지며,
    score vector와 filter 사유가 `RetrievalTrace`에 기록된다.
30. token 또는 risk budget으로 후보를 제외하면 `ContextBundle`에 누락 대상과 사유가
    기록되고 mandatory prerequisite는 조용히 잘리지 않는다.

## Current code mapping

| 불변식 | 현재 연결 지점 | 유지·보강할 계약 |
|---|---|---|
| L1 ToolGraph | `Case.solution.tool_graph` | L1은 복수 Tool node/edge를 허용하는 실행 그래프다. |
| Procedure hierarchy | `parent_case_id`, `parent_node_id`, `child_case_ids` | L2 이상 Procedure와 바로 아래 Procedure/L1 간 anchor 관계를 명시한다. |
| Derived Layer | `CaseStore.derive_layer()` | 계층 높이는 파생하되 L1/상위 Procedure의 의미는 바꾸지 않는다. |
| All-layer recall | `CaseStore._retrieval_candidates()` | 모든 live HEAD를 Layer 필터 없이 같은 후보군에 넣는다. |
| Hybrid seed retrieval | embedding map과 lexical score | 최신 Situation을 포함한 `QueryProfile`로 모든 Layer의 Procedure/ToolGraph seed를 함께 찾는다. |
| Ontology expansion | 현재 parent/child traversal helper | seed에서 prerequisite, alternative, revision, outcome 관계를 typed property path로 확장한다. |
| Situation rerank | 현재 similarity/quality score | semantic, state, tool, policy, evidence, validity, freshness를 분리한 score vector와 filter trace로 확장한다. |
| Context packing | 현재 recursive serialization | closure, 관련 branch, token/risk budget과 omission ledger를 가진 `ContextBundle`로 교체한다. |
| ReAct context | `chaeshin_retrieve` / `MemoryObservation` | Layer와 memory kind를 포함한 근거를 반환한다. |
| Case identity | 현재의 `case_id` | 각 immutable Case revision마다 공유되지 않는 ontology IRI/`case_id`로 유지한다. |
| Task identity | 현재 ReAct request/session context | 실제 작업마다 별도 Task individual과 고유 `task_id`를 생성하고 Case ID와 구분해야 한다. |
| Situation identity | `ProblemFeatures` | 독립된 Situation individual과 `inSituation` relation으로 승격하고 revision 연결 시 동일성을 검증해야 한다. |
| POMDP-inspired belief | 현재 `ProblemFeatures`와 Tool Observation | `RuntimeSituationSnapshot`, `SituationClaim`, unknown, confidence와 provenance로 승격하되 완전한 확률 모델을 강제하지 않는다. |
| Revision lineage | `previous_case_id`, `revision_index`, `is_head`, `root_case_id` | ontology의 `supersedes`, `mergedFrom`, `revertOf` relation 기반 DAG 및 atomic HEAD ref로 수렴하고 공통 root ID 의존은 제거해야 한다. |
| Evidence/version | `Outcome`, event log | case/run-scoped append-only evidence와 Case revision을 분리한다. |
| Governance | retain/revise/verdict 및 검색 후보 정책 | review state, 역할별 권한, ACL·tenant·quarantine gate를 명시적으로 강제한다. |
| Ontology source of truth | 현재 dataclass, JSON, SQLite row | RDF/OWL individual과 relation을 정본으로 삼고 SHACL로 mutation을 검증해야 한다. |
| Derived search views | embedding map, lexical text, graph traversal helper | ontology revision에 결속된 재생성 가능한 projection으로 관리해야 한다. |
| Runtime Situation | 현재 ReAct message와 domain별 context dict | Observation마다 새 Situation individual을 만들고 Tool 선택·재검색·trace에 연결해야 한다. |
