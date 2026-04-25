# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-04-26 — 아키텍처 업그레이드 + Zenodo archive

이 release부터 Zenodo가 자동으로 archive하고 DOI를 발급한다 — 인용 가능한 software artifact 단위.



### Graphs All the Way Down (후속)
- **`chaeshin_revise(case_id, graph, cascade=true)`** — 특정 레이어의 Tool Graph를 새로
  쓰고 다운스트림을 파급. 상위 그래프에서 사라진 노드에 매달려 있던 자식 케이스는
  자동으로 `outcome.status="pending"`으로 되돌아가며 `[cascade]` 로그가 남음. 자식
  삭제하지 않음 — 사람의 명시적 결정 원칙.
- `case_store.revise_graph()` — `added_nodes`, `removed_nodes`, `retained_nodes`,
  `orphaned_children`을 계산해 반환. 이벤트 로그에 `revise` 이벤트로 기록.
- 모니터 `/hierarchy`에 노드별 `⊞node·edge` 그래프 요약 배지 + `orphan` rose 뱃지
  + `↱parent_node_id` 앵커 표시. "그래프 구조가 계속 내려간다"는 걸 가시화.
- README/CLAUDE.md 리프레이밍: "각 레이어가 자체 그래프" → "노드를 쪼개면 또 그래프"
  (상위 레이어가 그래프면 하위도 그래프 — zoom-in 의미론).
- 의료 예시에 cascade 시나리오 추가: 복약 이슈로 L3 'plan' 그래프를 재작성 → 기존 L2
  "메트포르민 1차 시작"이 고아가 되어 pending 회귀. demo.py가 전체 동작을 실제로 출력.


### Added — 재귀 분해 & 관측성
- **재귀 깊이 무제한**. `CaseMetadata.depth` 신규 필드. `layer`는 자유 문자열 (L1=leaf, Ln=composite). 고정 3단계 제거 — tool로 해결될 때까지 분해.
- **Tri-state outcome** `Outcome.status: "success" | "failure" | "pending"`. `pending`이 기본 — retain 직후 verdict 없이는 성공/실패가 아닌 중간 상태.
- **사용자 verdict** `chaeshin_verdict(case_id, status, note)` — 응답 없으면 pending 유지. deadline 경과도 pending 유지(자동 실패 전환 금지).
- **Deadline 기반 대기** `metadata.wait_mode`(`"deadline"` 기본 2h / `"blocking"`) + `metadata.deadline_at`.
- **Diff 기반 CRUD** `chaeshin_update(case_id, patch)` 얕은 merge + changed_fields 반환, `chaeshin_delete(case_id, reason)`.
- **SQLite 백엔드 전환** `~/.chaeshin/chaeshin.db` (cases, events, hierarchy_edges, embeddings). 기존 JSON 자동 이관.
- **이벤트 로그** 모든 MCP 호출(retrieve/retain/update/delete/verdict/feedback/decompose)을 `events` 테이블에 기록.
- **모니터 UI** `/events` 타임라인(5초 자동갱신) + `/hierarchy` 재귀 트리(동적 레이어 필터 + pending/success/failure 필터 + hover verdict 버튼).
- **의료 도메인 예시** `examples/medical_intake/` — 신규 T2DM 환자 초진 시나리오. 재귀 분해 + pending verdict + FHIR R5 매핑 부록 + 실행 가능한 데모.

### Changed
- `chaeshin_retain` 기본 `outcome.status="pending"`, `wait_mode="deadline"`(7200s). 이전처럼 즉시 성공/실패 assume 하지 않음.
- `chaeshin_decompose` 반환 포맷: `layer_schema`가 고정 L1/L2/L3 → `{recursive: true, leaf, composite}` + `retain_protocol`에 재귀 분해 + verdict 룰 명시.
- `chaeshin_retrieve` 반환에 `pending` 배열 추가 — 유사 pending 케이스를 성공/실패와 분리해 노출.
- 모니터 `case-store.ts` JSON → better-sqlite3. 동일 DB를 Python MCP와 공유.

### Migration
- `m001_json_to_sqlite_l1.py` — 레거시 `cases.json` → SQLite + `layer=""` → `"L1"`.
- `m002_outcome_status.py` — 기존 케이스에 `outcome.status` 백필 (success bool 기반).

## [0.1.0] - 2026-03-25

### Added

- Core schema: `Case`, `ToolGraph`, `GraphNode`, `GraphEdge`, `ExecutionContext`
- CBR case structure following `(problem_features, solution, outcome, metadata)` tuple
- `GraphExecutor` — hybrid execution engine (code-based + LLM replan)
  - Parallel node execution support
  - Edge condition evaluation with `node.output.field == value` syntax
  - Loop detection and `max_loops` guard
  - Dynamic patient TODO generation from graph state
- `CaseStore` — CBR case storage with keyword-based retrieval
  - `retrieve()` with Jaccard similarity
  - `retain_if_successful()` with satisfaction threshold
  - JSON serialization/deserialization
- `GraphPlanner` — LLM-based graph creation, adaptation, and replanning
  - `create_graph()` from scratch
  - `adapt_graph()` to modify retrieved case for current situation
  - `replan_graph()` with diff-based graph modification
- Cooking example: kimchi stew chef agent
  - 9 cooking tools (알레르기체크, 재료확인, 썰기, 볶기, 끓이기, 간보기, 양념하기, 굽기, 담기)
  - 2 pre-built CBR cases (김치찌개, 된장찌개)
  - Full CBR cycle demo: Retrieve → Execute → Retain
