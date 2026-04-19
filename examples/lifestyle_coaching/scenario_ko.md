# 생활습관 코칭 — 만성피로 직장인 3개월 리셋

> Chaeshin v3를 **비의료, 비임상** 생활습관 코칭에 적용한 예시. 코치가 클라이언트의
> 패턴을 듣고 플랜을 설계하고, 클라이언트의 주간 체크인에 따라 그래프가 진화하는
> 과정을 다룬다.

**왜 이 예시인가.** 생활습관은 "했다/안 했다"가 바로 성공/실패가 아니다. 시도는
했는데 피드백이 애매하고, 몇 주가 지나야 뭐가 먹혔는지 보인다. 코치가 플랜을
고치는 일도 잦다. 이 도메인은 Chaeshin의 세 설계 결정을 그대로 요구한다:

1. **재귀적 그래프** — 목표는 하위 도메인으로, 하위 도메인은 실행 가능한 습관으로,
   결국 리프는 "앱 하나 켜기" 같은 단일 동작까지 내려간다.
2. **Tri-state outcome** — 주간 체크인에서 "애매했어요"가 기본값이다. 성공/실패를
   넘겨짚지 않는다.
3. **Cascading revise** — 플랜 중간 수정이 필연이다. 상위 그래프를 바꾸면 기존
   습관 중 뭐가 무효가 되는지 자동으로 표시되어야 한다.

---

## 목차

1. [클라이언트 프로필](#1-클라이언트-프로필)
2. [도구 레지스트리](#2-도구-레지스트리)
3. [전체 케이스 트리 — L4 → L1](#3-전체-케이스-트리--l4--l1)
4. [시나리오 A — 12주 성공 경로](#4-시나리오-a--12주-성공-경로)
5. [시나리오 B — 연락 두절 (pending 유지)](#5-시나리오-b--연락-두절-pending-유지)
6. [시나리오 C — 번아웃 신호 → 플랜 자체 실패](#6-시나리오-c--번아웃-신호--플랜-자체-실패)
7. [Cascading revise — 2주차 플랜 수정](#7-cascading-revise--2주차-플랜-수정)
8. [재사용 — 유사 클라이언트 인입](#8-재사용--유사-클라이언트-인입)

---

## 1. 클라이언트 프로필

```
Client: 박OO (34, 남)
표면적 호소: "올해는 진짜 몸 좀 챙기고 싶어요. 만성피로가 너무 심해요."
```

| 항목 | 값 | 어떻게 파악 |
|------|------|-----------|
| 직업 | 스타트업 PM, 주당 근무 60-70h | 인테이크 대화 |
| 수면 | 취침 2-3시, 기상 8시, 주말 10h 몰아자기 | 수면 앱 백데이터 2주 |
| 운동 | 지난 6개월 0회 | 자기보고 |
| 식사 | 아침 거름 / 점심 배달 / 저녁 야근 도시락 or 술자리 | 3일 식사 사진 |
| 음주 | 주 3-4회, 업무 관련이 절반 | 자기보고 |
| 스트레스 | 자기평가 8/10, PHQ-2 = 2 (임상역치 아님) | 간이 스크리닝 |
| 이전 시도 | 헬스장 3개월 끊었다가 1주 가고 포기 × 2회 | 인테이크 대화 |
| 진짜 동기 | 돌 지난 아이. "아빠가 먼저 지쳐있는 게 싫어요." | 2차 인테이크 |

**코치의 판단**. 교과서적인 "주 5회 유산소 + 정상 식단" 처방은 이 사람에게
두 번 실패한 방식 그대로다. 진짜 제약은 시간도 체력도 아니고 **심리적 에너지
여유가 없다는 것** — 번아웃 직전 상태. 어떤 계획도 "이것까지 해야 한다"로
느껴지는 순간 역풍이 분다. 최소 부하로 시작해서 탄력을 만드는 전략으로 간다.

---

## 2. 도구 레지스트리

| 도구명 | 설명 | 입력 | 출력 |
|--------|------|------|------|
| `daily_energy_log` | 하루 끝 에너지 레벨 기록 (1-5) | `{client_id, level, note}` | `{logged_at}` |
| `sleep_snapshot` | 수면 앱에서 지난밤 데이터 수집 | `{client_id}` | `{duration, efficiency, bedtime}` |
| `meal_snapshot` | 식사 사진 1장 전송 (라벨 X) | `{client_id, photo_ref}` | `{logged_at}` |
| `habit_checkin` | 주간 체크인 — 뭐가 쉬웠고 뭐가 막혔는지 | `{client_id, week}` | `{kept: [...], skipped: [...], notes}` |
| `walk_reminder` | "지금 10분만 걷자" 푸시 | `{client_id, time}` | `{notification_id}` |
| `content_nudge` | 짧은 글/영상 추천 (수면위생, 호흡 등) | `{client_id, topic}` | `{content_id}` |
| `workout_propose` | 부하 낮은 운동 제안 (1개만) | `{client_id, minutes, equipment}` | `{exercise, steps}` |
| `meal_rule_propose` | 한 줄짜리 식사 규칙 제안 | `{client_id, context}` | `{rule_text}` |
| `coach_check` | 코치가 비동기로 상태 확인 | `{client_id}` | `{risk_signal, note}` |
| `session_book` | 다음 코칭 세션 예약 | `{client_id, when}` | `{session_id}` |

---

## 3. 전체 케이스 트리 — L4 → L1

```
L4  "3개월 생활 리셋"                                             [depth=3]
│   graph.nodes = [intake, stratify, plan, accountability]
│   graph.edges = intake → stratify → plan → accountability
│
├── L3  "intake — 현재 패턴 파악"                                 [depth=2]
│   ├── L2  "수면 베이스라인"                                      [depth=1]
│   │   └── L1  sleep_snapshot × 14일 자동 수집                    [leaf]
│   ├── L2  "식사 패턴 스냅샷"                                     [depth=1]
│   │   └── L1  meal_snapshot × 3일 (기록만, 평가 X)
│   ├── L2  "에너지·기분 베이스라인"                               [depth=1]
│   │   └── L1  daily_energy_log 14일
│   └── L2  "진짜 동기 찾기"                                       [depth=1]
│       └── L1  2차 인테이크 대화 (코치 수기 노트)
│
├── L3  "stratify — 리스크 & 현실성"                               [depth=2]
│   ├── L2  "번아웃 신호 체크"                                     [depth=1]
│   │   └── L1  PHQ-2 + 자기평가 스트레스 점수
│   ├── L2  "반복 실패 패턴 분석"                                  [depth=1]
│   │   └── L1  코치 수기 분석 — "헬스장 = trigger"
│   └── L2  "최소 실행 가능 단위 확정"                             [depth=1]
│       └── L1  "하루 총 15분 부하로 시작" 합의
│
├── L3  "plan — 3개월 구조"                                        [depth=2]
│   │   (intake + stratify 결과 기반으로 인스턴스화. 과한 것 배제.)
│   ├── L2  "수면 앵커"                                            [depth=1]
│   │   ├── L1  "취침 1시간 전 카페인/술 차단" 규칙 1개
│   │   └── L1  content_nudge(topic="수면위생 3분 영상")
│   ├── L2  "움직임 앵커 — 매일 10분"                              [depth=1]
│   │   ├── L1  workout_propose(minutes=10, equipment="none")
│   │   └── L1  walk_reminder(time="점심 직후")
│   ├── L2  "식사 규칙 1개"                                        [depth=1]
│   │   └── L1  meal_rule_propose(context="아침 공복") → "물 한 컵 + 바나나"
│   └── L2  "술 — 주 1회 '안 마시는 날' 정하기"                    [depth=1]
│       └── L1  "매주 화요일 = 물의 날" 합의
│
└── L3  "accountability — 이탈 방지망"                             [depth=2]
    ├── L2  "주간 체크인"                                          [depth=1]
    │   └── L1  habit_checkin(매주 일요일 저녁)
    ├── L2  "2주차·6주차 재조정"                                   [depth=1]
    │   ├── L1  session_book(when="2주 후")
    │   └── L1  session_book(when="6주 후")
    └── L2  "조용한 안전망"                                        [depth=1]
        └── L1  coach_check(monthly, 연락 끊어지면 먼저 연락)
```

**설계 포인트**

- **최소 부하 원칙**. L3 "plan" 아래 L2는 각자 "1개씩만" 규칙. "수면 앵커"는
  카페인 차단 하나, "움직임"은 10분, "식사"는 한 줄짜리 규칙. 초과하면 실패
  확률이 폭증한다는 게 이 클라이언트 이력에서 이미 드러났다.
- **반복 실패를 데이터로 다룸**. "헬스장 등록 → 1주 가고 포기" 패턴은 L2
  "반복 실패 패턴 분석"에 명시 저장. 앞으로 이 클라이언트의 retrieve에서
  "헬스장 기반 플랜"은 `warnings`로 나오도록 함.
- **"안전망"을 명시 레이어로**. 대부분의 앱 기반 코칭이 실패하는 지점 — 이탈
  후 복귀. `coach_check`가 자동으로 월 1회 트리거되어 연락이 끊기면 코치가
  먼저 연락하는 패턴을 그래프에 박아둔다.

---

## 4. 시나리오 A — 12주 성공 경로

### T0 — 인테이크 당일

1. 코치가 `chaeshin_retrieve(query="30대 직장인 만성피로 리셋", keywords="번아웃,반복실패,스타트업")` 호출.
   - 유사 케이스 1건, similarity 0.76. "과부하형 리셋 플랜 실패" 가 `warnings`에 등장. 교훈을 읽음.

2. `chaeshin_decompose(query=..., tools="sleep_snapshot,workout_propose,...")` 로 분해 프로토콜 수신.

3. 코치(또는 호스트 AI)가 위 트리 전체를 재귀 retain. **전부 pending**으로 저장.
   - L4 root: `wait_mode="deadline"`, `deadline_seconds=12*7*24*3600`
   - L3 "plan": `deadline_seconds=2*7*24*3600` (2주 뒤 재조정 세션이 1차 마일스톤)

### T+1주 — 첫 체크인

- 클라이언트: "점심 걷기 4번 했어요. 카페인은 한 번 실수. 10분 운동은 3번."
- 코치 해석: **아직 성공/실패 단정 안 함**. 1주는 시작일 뿐.
- `chaeshin_feedback(case_id=<L2 "움직임 앵커">, feedback="점심 걷기는 자연스러움, 10분 운동은 '저녁에 하려고 미뤘다가 까먹음' 패턴", feedback_type="modify")`
- L2의 feedback_count +1, status는 **pending 유지**.

### T+2주 — 재조정 세션 (cascade)

§7에서 자세히. 10분 홈운동이 작동 안 함을 인정하고 L3 "plan" 그래프 수정.

### T+6주 — 중간 세션

- 수면 평균 5.5h → 6.5h. 점심 걷기 주 5회 유지.
- 여전히 HbA1c 같은 단일 종료점은 없음. 코치는 여러 지표를 종합적으로 본다.
- 아직 pending — 12주 지점에서 전체 verdict 내릴 계획.

### T+12주 — 종료 세션

- 클라이언트 자기 평가: 에너지 3→4, 아침 기상 알람 없이 3회/주.
- 아내 피드백 "주말에 애랑 더 잘 놀아요."
- 코치 `chaeshin_verdict(case_id=<L4 root>, status="success", note="지속 가능한 습관 3개 정착. 수면 1h 증가. 본인 말: '다음 단계 가보고 싶어요.'")`
- 이 verdict는 L4만 success로 전환. 자식 L3/L2/L1 중 **실제로 유지된 것만**
  코치가 개별적으로 verdict success로 마킹. "술 — 주 1회 안 마시는 날"은
  8주차에 포기했으므로 `verdict=failure, note="술자리 주도권 없음 — 대안
  필요"`로 실패 기록.

실패를 지우지 않는 이유: 다음 유사 클라이언트가 올 때 "이 플랜에서 술 규칙은
안 먹혔다"는 신호가 자연스럽게 warning으로 뜨도록.

---

## 5. 시나리오 B — 연락 두절 (pending 유지)

4주차부터 주간 체크인 무응답. 세션도 no-show.

- 6주차 자동 `coach_check` 트리거 — 코치가 먼저 연락. 답 없음.
- 12주 deadline 경과. 케이스는 **pending 그대로**.
  - 이게 핵심. 코치는 "실패로 클로즈"를 임의로 하지 않는다. "잠수"라는 이유로
    실패 라벨을 붙이면 다음 유사 클라이언트에게 잘못된 warning이 뜰 수 있다.
- `chaeshin_stats.overdue_pending` +1. 모니터 `/hierarchy`에서 pending
  배지가 진한 호박색(overdue)으로 변함.
- 코치의 월간 리뷰 루틴: overdue pending 목록을 훑고 연락 시도 / 종료 결정.
  최종적으로 `chaeshin_verdict(status="failure", note="3회 연락 시도 무응답,
  클로즈")`를 수동으로 기록.

**"응답 없음"은 실패 아님**. 이걸 자동화하지 않는 게 설계다.

---

## 6. 시나리오 C — 번아웃 신호 → 플랜 자체 실패

가상의 대안 경로. 코치가 유사 케이스 조회를 건너뛰고 표준 플랜 사용:

- L3 "plan" 에 **주 4회 홈 HIIT + 주 1회 헬스장**을 그대로 집어넣음 (과거 실패 패턴과 동일).
- 2주차 체크인에서 "하나도 못 했어요. 일 끝나면 아무것도 못 할 힘이 없어요."
- 코치가 L3 plan에 대해 `chaeshin_verdict(status="failure", note="번아웃 직전
  클라이언트에게 주 5회 운동 처방은 비현실. 최소 부하 원칙 위반.")`
- 이 L3는 미래 retrieve에서 경고로 등장 → 다음 번아웃 신호 클라이언트에서
  반복 방지.

---

## 7. Cascading revise — 2주차 플랜 수정

**2주차 재조정 세션**. 체크인 데이터:
- "10분 홈운동"은 3주 합쳐 2회. 자꾸 저녁으로 미루다 까먹음.
- "점심 걷기"는 주 5회, 자연스럽게 되고 있음.
- "카페인 차단"은 주 4일 지킴.

코치 진단: 홈운동 노드는 위치가 틀렸다. 걷기는 잘 붙으니 그걸 기반으로 이식한다.
**L3 "plan"의 그래프 자체를 손본다** — 단순 feedback이 아니라:

```
수정 전:  sleep → movement → meal → alcohol
수정 후:  sleep → walking_core → strength_snack → meal → alcohol
                 └── "movement" 쪼개기: "걷기 늘리기"(앵커) + "1분 스트렝스 스낵"(곁가지)
```

```python
chaeshin_revise(
    case_id=L3_plan_id,
    graph={
        "nodes": [
            {"id": "sleep", "tool": "compose"},
            {"id": "walking_core", "tool": "compose",
             "note": "점심 걷기 유지 + 20분으로 연장"},
            {"id": "strength_snack", "tool": "compose",
             "note": "이 닦을 때 스쿼트 10회 — 루틴에 끼워넣기"},
            {"id": "meal", "tool": "compose"},
            {"id": "alcohol", "tool": "compose"},
        ],
        "edges": [
            {"from": "sleep", "to": "walking_core"},
            {"from": "walking_core", "to": "strength_snack"},
            {"from": "strength_snack", "to": "meal"},
            {"from": "meal", "to": "alcohol"},
        ],
    },
    reason="홈운동 노드가 작동 안 함. 잘 붙은 걷기를 앵커로 확장, 의지 안 드는 스트렝스로 재배치.",
    cascade=True,
)
```

응답:
```json
{
  "added_nodes": ["walking_core", "strength_snack"],
  "removed_nodes": ["movement"],
  "retained_nodes": ["sleep", "meal", "alcohol"],
  "orphaned_children": ["<L2 '움직임 앵커 — 매일 10분' case_id>"]
}
```

자동으로 일어나는 일:

1. **L2 "움직임 앵커 — 매일 10분"** 이 고아화
   - `outcome.status`가 pending으로 되돌아감. `feedback_log`에
     `[cascade] parent node 'movement' removed by revise; needs review`
   - 모니터 `/hierarchy`에서 rose **`orphan`** 배지로 노출
   - 코치는 이걸 보고 결정: (a) 내용을 걷기 중심으로 수정한 뒤 `walking_core`에
     재연결, (b) 기록 의미로 남긴 채 failure verdict 기록, (c) delete.
     이 클라이언트에겐 (b)를 선택 — "10분 홈운동은 이 사람에게 안 먹힌다"는
     실패 신호가 retrieve warning에 앞으로 뜨도록.

2. **새 노드 `walking_core`, `strength_snack`** 이 확장 대상으로 반환
   - 코치가 각각 새 L2 케이스를 retain:
     - `L2 "점심 걷기 20분으로 확장"` (parent_node_id="walking_core")
     - `L2 "양치할 때 스쿼트 10회"` (parent_node_id="strength_snack")

3. **retained `sleep`, `meal`, `alcohol`** 은 건드리지 않음. 되고 있는 건
   그대로 둔다.

4. 이벤트 로그에 `revise` 이벤트 → "2주차에 누가·왜 그래프를 수정했는지"
   감사 가능. 3개월 뒤 회고 때 "이 수정이 전환점이었다"고 되짚을 수 있다.

**이게 코칭에서 의미 있는 이유.** 수정이 무한히 쌓이지 않는다 — 위에서 내려오는
구조적 수정은 아래 습관 중 무효가 된 것을 자동으로 "검토 필요"로 표시한다.
코치는 삭제 여부를 직접 결정하므로 기록은 잃지 않는다. 클라이언트의 개인사
자체가 자산이 된다.

---

## 8. 재사용 — 유사 클라이언트 인입

6개월 후, 31세 여성 스타트업 마케터. 야근, 운동 0, 번아웃 근접. 유사 프로필.

```python
result = chaeshin_retrieve(
    query="30대 스타트업 만성피로 생활 리셋",
    keywords="번아웃,야근,반복실패",
    include_children=True,
    top_k=2,
)
```

- `successes[0]`: 박OO의 L4 트리, similarity 0.79
  - children 로드 시 "점심 걷기 → 20분 확장"이 L2로, "양치 시 스쿼트"가 L1로 전개
- `warnings`:
  - "주 5회 HIIT 플랜" L3 (시나리오 C의 실패 기록) — 같은 실수 방지
  - "10분 홈운동" L2 (§7에서 failure로 클로즈된 것) — 대안 필요 신호

코치는 박OO 플랜을 베이스로, 이 클라이언트의 개인 제약(새벽 미팅, 자차 없음,
반려견 있음)에 맞춰 diff 반영:

```python
# 걷기를 반려견 산책으로 대체
chaeshin_update(
    case_id=<new client's walking L2>,
    patch={
        "problem_features": {"constraints": ["저녁 반려견 산책 30분 고정"]},
    },
)
```

**데이터가 자산화되는 구조**. 박OO의 12주는 그의 3개월로 끝나지 않는다.
고아화된 실패 L2까지 포함해 다음 클라이언트의 시작점이 된다. 코치의 개인
경험이 팀 전체의 검증된 패턴으로 누적된다.

---

## 맺음말

이 시나리오에 의료 용어가 한 마디도 필요 없었다. Chaeshin의 세 설계 결정이
생활습관 코칭이라는 **일반 도메인에서도 그대로 유효**하다:

1. **재귀 분해** — "리셋"이라는 추상 목표가 "양치할 때 스쿼트 10회"까지
   내려온다. 중간 레이어를 건너뛰면 계획이 실행 불가능해진다.
2. **Pending이 기본** — "해봤어요, 애매해요"가 디폴트. 성공/실패는 사람이
   명시한다.
3. **상위 그래프 수정 → 다운스트림 반응** — 2주차 재조정에서 움직임 구조를
   통째로 바꿔도, 되고 있던 수면·식사 습관은 건드리지 않고 영향받는 것만
   자동으로 "검토 필요"로 표시된다.

의료 도메인에서 이 패턴이 "높은 실수 비용" 때문에 선택되었다면, 생활습관
코칭에서는 "지속 가능성이 곧 성공 지표"이기 때문에 선택된다. 구조는 같고,
데이터가 쌓일수록 코치가 더 나은 플랜을 제안할 수 있다.

---

## 부록 — 실행 가능한 데모

```bash
uv run python -m examples.lifestyle_coaching.demo
```

`demo.py`가 보여주는 것:
1. 박OO 프로필로 L4→L1 트리를 pending으로 저장
2. 1주차 feedback만 기록 (verdict 보류)
3. 2주차 revise — L3 plan 그래프 수정 + 움직임 L2 고아화
4. 고아 L2에 failure verdict + 12주차 L4 success verdict
5. 유사 클라이언트(이OO) 내원 → retrieve successes + warnings 확인
