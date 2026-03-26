# CBR Case Schema Reference

## Case = (problem_features, solution, outcome, metadata)

### problem_features

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `request` | string | 사용자 원본 요청 | "김치찌개 만들어줘" |
| `category` | string | 문제 카테고리 | "찌개류" |
| `keywords` | list[str] | 핵심 키워드 (검색용) | ["김치", "찌개", "묵은지"] |
| `constraints` | list[str] | 제약 조건 | ["매운거 OK", "2인분"] |
| `context` | dict | 도메인별 추가 정보 | {"servings": 2, "available_ingredients": [...]} |

### solution

| 필드 | 타입 | 설명 |
|------|------|------|
| `tool_graph` | ToolGraph | 실행 설계도 |

#### ToolGraph

| 필드 | 타입 | 설명 |
|------|------|------|
| `nodes` | list[GraphNode] | 도구 호출 노드들 |
| `edges` | list[GraphEdge] | 노드 간 연결 |
| `parallel_groups` | list[list[str]] | 동시 실행 가능 노드 그룹 |
| `entry_nodes` | list[str] | 시작 노드 ID들 |
| `max_loops` | int | 무한 루프 방지 (기본: 3) |

#### GraphNode

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `id` | str | 고유 ID | "n1" |
| `tool` | str | 도구 이름 | "볶기" |
| `params_hint` | dict | 예상 파라미터 | {"재료": "돼지고기+묵은지"} |
| `note` | str | 목적 설명 | "베이스 볶기" |

#### GraphEdge

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `from_node` | str | 출발 노드 ID | "n1" |
| `to_node` | str? | 도착 노드 ID (null=특수액션) | "n2" 또는 null |
| `condition` | str? | 조건식 | "n1.output.ok == true" |
| `action` | str? | 특수 액션 (to_node=null일 때) | "emergency_exit" |
| `priority` | int | 평가 우선순위 | 0 |
| `note` | str | 설명 | "알레르기 시 중단" |

### outcome

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | bool | 성공 여부 |
| `result_summary` | str | 결과 요약 |
| `tools_executed` | int | 실행된 도구 수 |
| `loops_triggered` | int | 발생한 루프 수 |
| `total_time_ms` | int | 총 실행 시간 (ms) |
| `user_satisfaction` | float | 사용자 만족도 (0~1) |
| `details` | dict | 도메인별 상세 |

### metadata

| 필드 | 타입 | 설명 |
|------|------|------|
| `case_id` | str | 고유 ID (UUID) |
| `created_at` | str | 생성 시각 (ISO8601) |
| `updated_at` | str | 수정 시각 |
| `used_count` | int | 사용 횟수 |
| `avg_satisfaction` | float | 평균 만족도 |
| `source` | str | 출처 |
| `version` | int | 버전 |
| `tags` | list[str] | 태그 |
