# Architecture — 채신(Chaeshin) 아키텍처

## 전체 흐름

```
사용자 요청: "김치찌개 2인분 해줘"
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│                    1. Retrieve (CBR)                     │
│                                                         │
│  사용자 요청을 임베딩 → VectorDB에서 유사 케이스 검색     │
│  결과: 김치찌개 Tool Graph (nodes + edges)               │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                    2. Adapt (Planner)                    │
│                                                         │
│  검색된 그래프를 현재 상황에 맞게 LLM이 조정              │
│  (재료 다르면 노드 수정, 제약 있으면 엣지 추가)           │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   3. Execute (Engine)                    │
│                                                         │
│  그래프 노드를 순서대로 실행                              │
│  - 병렬 가능 노드는 동시 실행                            │
│  - edge condition으로 다음 노드 결정                     │
│  - 루프 발생 시 max_loops까지 허용                       │
│                                                         │
│  예외 발생 시:                                           │
│  ┌─────────────────────────────────┐                    │
│  │ 4. Replan (LLM)                │                    │
│  │ diff 기반 그래프 수정           │                    │
│  │ (노드 추가/삭제, 엣지 변경)     │                    │
│  └─────────────────────────────────┘                    │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                    5. Retain (CBR)                       │
│                                                         │
│  성공한 케이스를 다시 VectorDB에 저장                     │
│  (다음에 비슷한 요청이 오면 이 그래프를 재사용)            │
└─────────────────────────────────────────────────────────┘
```

## 핵심 컴포넌트

### schema.py — 데이터 모델

CBR 케이스의 4-tuple 구조:

```
Case = (problem_features, solution, outcome, metadata)
```

- `ProblemFeatures`: 문제 정의 (요청, 카테고리, 키워드, 제약)
- `Solution`: Tool Graph (노드 + 엣지 = 실행 설계도)
- `Outcome`: 실행 결과 (성공 여부, 만족도, 실행 시간)
- `CaseMetadata`: 관리 정보 (생성일, 사용 횟수, 버전)

그래프와 실행 상태의 분리:

- `ToolGraph`: 불변 설계도 (CBR에서 가져온 그대로)
- `ExecutionContext`: 가변 커서 (각 노드의 상태, 결과, 이력)

### graph_executor.py — 실행 엔진

하이브리드 방식 (방식 C):

1. **코드 자동 처리**: edge condition 평가, 다음 노드 결정, 루프 감지
2. **LLM 위임**: 매칭되는 edge가 없을 때만 `on_replan` 콜백 호출

실행 루프:
```
while not completed:
    ready_nodes = find_ready_nodes()
    parallel, sequential = classify(ready_nodes)
    execute_parallel(parallel)
    for node in sequential:
        execute(node)
        advance(node)  # edge condition → 다음 노드
```

### case_store.py — CBR 저장소

CBR 4R 사이클:
- **Retrieve**: 키워드 Jaccard 유사도 또는 임베딩 코사인 유사도
- **Reuse**: 검색된 케이스의 Tool Graph를 그대로 사용
- **Revise**: Planner가 현재 상황에 맞게 수정
- **Retain**: 성공 + 만족도 기준 충족 시 저장

### planner.py — LLM 기반 플래너

3가지 모드:
- `create_graph()`: 케이스가 없을 때 처음부터 생성
- `adapt_graph()`: 검색된 케이스를 현재 상황에 맞게 수정
- `replan_graph()`: 실행 중 예외 시 diff로 수정

## Edge Condition 문법

```
노드ID.output.필드 연산자 값
```

지원 연산자: `==`, `!=`, `>`, `>=`, `<`, `<=`

예시:
```
n1.output.allergy_detected == false
n6.output.taste == 싱거움
n4.output.evidence_level != HIGH
```

## 그래프 수정 Diff 형식

```json
{
  "added_nodes": [{"id": "n5-1", "tool": "간보기"}],
  "removed_nodes": [],
  "added_edges": [{"from": "n5", "to": "n5-1"}],
  "removed_edges": [{"from_node": "n5", "to_node": "n6"}],
  "reasoning": "과조리 감지로 추가 간보기 필요"
}
```
