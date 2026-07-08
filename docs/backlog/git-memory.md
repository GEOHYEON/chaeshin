# Backlog — git식 케이스 메모리

케이스 메모리를 git처럼 다루는 모델의 미구현 영역. 각 항목은 **언제 필요해지는가(trigger)**와
**구현 방법(method)**을 같이 적는다. 현재 닫힌 것 → 열린 것 순.

## 현재 구현된 것 (참고)

| git | chaeshin | 위치 |
|-----|----------|------|
| commit | `revise` → `_commit_graph_revision` (HEAD를 snapshot으로 보존 후 교체) | `case_store.py` |
| HEAD | `metadata.is_head` (검색 후보는 HEAD만) | `_retrieval_candidates` |
| parent / log | `previous_case_id` 체인 / `get_history` | `case_store.py` |
| diff | `diff_versions` / `_graph_diff` | `case_store.py` |
| revert | `revert(to_index)` / `revert_to_tag` | `case_store.py` |
| blame | `blame` — 노드별 도입 리비전 | `case_store.py` |
| tag | `tag` / `list_tags` (name → revision_index) | `case_store.py` |

지금은 **선형 버전 라인**: root 하나당 살아있는 HEAD는 정확히 1개. 아래는 그 가정을 깨야 열린다.

---

## 1. Branch — 분기 라인

**Trigger.** 같은 케이스를 버리지 않고 두 갈래로 실험해야 할 때. 예: 검증된 치료 플랜
그래프(HEAD)는 그대로 두고, "약을 바꿔보는" 대안 플랜을 별도 라인으로 키우며 둘 다
retrieve 후보로 남기고 싶을 때. 지금은 revise가 HEAD를 제자리에서 덮으므로 대안을
병렬 보존할 수 없다.

**Method.**
- `metadata`에 `branch_name`(기본 `"main"`) 추가. `(root_case_id, branch_name)`당 HEAD 1개로 유일성 보장.
- `branch(case_id, name)` — 현재 HEAD를 deepcopy해 새 `case_id`·`root_case_id`(원본 유지)·
  `branch_name=name`·`is_head=True`로 분기. `previous_case_id`는 분기점 snapshot을 가리킴.
- `_resolve_head`·`_retrieval_candidates`를 branch 인자로 필터. **검색 기본은 main HEAD만** —
  안 그러면 실험 라인이 운영 retrieve를 오염시킴(의료 도메인 리스크). branch 라인은 명시 조회 시에만.
- 주의: 자식 케이스(`parent_case_id`)는 어느 branch에 속하는지 모호해짐 → branch별 자식 복제는
  비용 큼. 우선은 **그래프만 분기, 자식은 main 공유**로 최소화하고 cascade는 main에서만.

## 2. Merge — 라인 병합

**Trigger.** 분기 라인이 검증(verdict=success)되어 main으로 합칠 때. Branch 없이는 무의미하므로 **1번에 종속**.

**Method.**
- 최소형: `merge(case_id, from_branch)` = from_branch HEAD 그래프를 main HEAD에 `revert`처럼
  새 커밋으로 얹는 fast-forward/overwrite. 노드 단위 3-way 병합은 범위 밖(충돌 해소 UX가 큼).
- 3-way가 필요해지는 trigger: 두 라인이 **서로 다른 노드 집합을 동시에** 키웠고 둘 다 살리고 싶을 때.
  그때 `_graph_diff`를 공통 조상(merge-base = 분기점 snapshot) 기준으로 양쪽 적용 →
  같은 node id에 다른 내용이면 `conflict` 리스트 반환, 사람이 결정. **그전까진 만들지 말 것.**

## 3. Bisect — outcome가 뒤집힌 리비전 찾기

**Trigger.** 여러 번 revise한 케이스가 어느 시점부터 verdict=failure로 돌기 시작했는지,
"어느 그래프 변경이 회귀를 유발했나"를 찾고 싶을 때.

**Method.**
- 전제: 리비전별 verdict 신호가 있어야 함. 지금 verdict는 **HEAD outcome 한 곳**만 기록 →
  snapshot에는 그 시점 outcome이 박제돼 있으므로 history를 훑으면 status 추이는 읽힌다.
- `bisect(case_id)` = history(오래된→최신)에서 `outcome.status`가 success→failure로 바뀐
  첫 경계 리비전과 그 `diff_versions`(직전↔해당)를 반환. 이진탐색까지 갈 필요 없이 선형 스캔으로 충분
  (히스토리 길이가 수천이 아닌 한). 길어지면 그때 binary search.

## 4. (옵션) Monitor에 tag/blame 노출

**Trigger.** 운영자가 UI에서 승인 리비전을 이름표로 보거나 노드 도입 시점을 보고 싶을 때.

**Method.** `chaeshin-monitor`의 `/hierarchy`(또는 케이스 상세)에서 `metadata.tags`를 배지로,
blame은 노드 hover 시 `introduced_at_index`를 표시. OSS upstream PR로 기여(사내 fork 금지 규칙).
서버 변경 없음 — 이미 저장된 필드만 읽음.
