# 임상 생활습관 문진 & 맞춤 계획 — 현실 시나리오

> Chaeshin v3 (재귀 분해 + tri-state outcome + 사용자 verdict)을 의료 도메인에서
> 실제 사용하는 워크스루. 신규 제2형 당뇨병 환자 초진 상황을 다룬다.

**왜 이 예시인가.** 의료는 결과가 몇 주~몇 달 뒤에 확인된다. "계획을 세웠다"는 것
자체로 성공도 실패도 아닌 **pending** 상태다. Chaeshin의 tri-state outcome과
deadline 기반 verdict 대기는 이 도메인 그대로를 모델링한다.

---

## 목차

1. [환자 프로필](#1-환자-프로필)
2. [도구(Tool) 레지스트리](#2-도구tool-레지스트리--fhir-매핑-포함)
3. [전체 케이스 트리 — L4 → L1](#3-전체-케이스-트리--l4--l1)
4. [시나리오 A — 성공 경로](#4-시나리오-a--성공-경로-12주-뒤-verdict-success)
5. [시나리오 B — 중간 상태 유지 (lost to follow-up)](#5-시나리오-b--중간-상태-pending-유지)
6. [시나리오 C — 실패 → 안티패턴 등록](#6-시나리오-c--실패--안티패턴-등록)
7. [Cascading revise — 상위 그래프 재작성](#7-cascading-revise--의료진이-상위-그래프를-재작성하면)
8. [재사용 — 유사 환자 내원](#8-재사용--유사-환자-내원)
9. [FHIR R5 리소스 매핑 부록](#9-fhir-r5-리소스-매핑-부록)

---

## 1. 환자 프로필

```
Patient: 김OO (45M, 익명)
Chief complaint: 건강검진 결과 상담 — "혈당이 높다고 나왔어요"
```

| 항목 | 값 | 출처 |
|------|------|------|
| HbA1c | 7.2% | 외부 검진 (LOINC 4548-4) |
| FBS | 142 mg/dL | 외부 검진 (LOINC 1558-6) |
| BMI | 28.4 | 측정 (LOINC 39156-5) |
| BP | 134/86 | 측정 (LOINC 85354-9) |
| 기존 진단 | 없음 (신환 T2DM) | — |
| 복용약 | 없음 | — |
| 직업 | 물류센터 야간 근무 (3교대) | 문진 |
| 가족력 | 모 T2DM, 부 AMI 58세 | 문진 |
| 흡연/음주 | 전흡연(5년 전 금연) / 주 2회 소주 1병 | 문진 |
| 경제 상황 | 외벌이, 주 70시간 근무 — "야식 아니면 편의점" | 문진 |

**이 환자의 진짜 어려운 부분**: 교과서 식단·운동 처방은 야간 3교대 + 경제적 제약에서
작동하지 않는다. 일반적인 "생활습관 교정 → 3개월 재검" 경로는 실패 확률이 높다.
Chaeshin은 이 개별성을 케이스 트리로 포착한다.

---

## 2. 도구(Tool) 레지스트리 — FHIR 매핑 포함

초진 에이전트가 호출할 수 있는 도구. 각 도구는 입력 → 출력 + 선택적으로 FHIR 리소스를 생성한다.

| 도구명 | 설명 | 입력 | 출력 (요약) | FHIR 리소스 |
|--------|------|------|-------------|-------------|
| `dietary_recall_24h` | 24시간 식이 회상 수집 | `{patient_id}` | `{meals: [...], kcal_est, macro}` | Observation (LOINC 9271-8) |
| `food_security_screen` | 식품 불안정성 스크리닝 (HFSSM 2문항) | `{patient_id}` | `{score: 0-2, insecure: bool}` | Observation (LOINC 88121-9) |
| `gpaq_activity` | GPAQ 신체활동 문진 | `{patient_id}` | `{met_minutes_week, sedentary_hours}` | Observation (LOINC 82580-1) |
| `audit_c` | AUDIT-C 알코올 스크리닝 | `{patient_id}` | `{score, risk_level}` | Observation (LOINC 75624-7) |
| `sleep_chronotype` | 수면/교대근무 평가 | `{patient_id}` | `{hours, shift_pattern, quality}` | Observation (LOINC 93832-4) |
| `motivation_readiness` | 변화단계(TTM) 평가 | `{patient_id, domain}` | `{stage: pre|contemp|prep|action}` | Observation (custom code) |
| `cvd_risk_calc` | ASCVD 10년 위험도 | `{age, sex, bp, chol, smoker, dm}` | `{risk_pct, category}` | RiskAssessment |
| `medication_propose` | 약물 초기 선택 제안 | `{hba1c, comorbid, prefs}` | `{drug, dose, rationale, contraindications}` | MedicationRequest |
| `meal_plan_tailored` | 제약조건 기반 식단 설계 | `{budget, shift, preferences, constraints}` | `{weekly_plan, grocery_list, cost}` | CarePlan.activity |
| `activity_plan_shift` | 교대근무 적응형 운동 처방 | `{shift_pattern, physical_ability}` | `{weekly_plan, pre/post_shift_splits}` | CarePlan.activity |
| `goal_set` | SMART 목표 생성 | `{domain, baseline, target, timeline}` | `{goal_id, measurable}` | Goal |
| `followup_schedule` | 후속 방문/검사 예약 | `{patient_id, interval, tests}` | `{appointment_id, lab_orders}` | Appointment + ServiceRequest |
| `patient_message_send` | 환자 메시지/리마인더 예약 | `{patient_id, template, schedule}` | `{communication_id}` | Communication |

---

## 3. 전체 케이스 트리 — L4 → L1

```
L4  "신환 T2DM 초진 — 개별 맞춤 관리 계획 수립"                     [depth=3]
│   graph.nodes = [intake, stratify, plan, followup]
│   graph.edges = intake→stratify→plan→followup
│
├── L3  "lifestyle intake"                                         [depth=2]
│   │   graph.nodes = [diet, activity, sleep, substance, motivation]
│   │
│   ├── L2  "식이 평가"                                            [depth=1]
│   │   ├── L1  dietary_recall_24h                                 [depth=0 / leaf]
│   │   ├── L1  food_security_screen
│   │   └── L1  한국 식단 이슈 체크 (김치 나트륨 / 탄수 비중)
│   │
│   ├── L2  "신체활동 평가"                                        [depth=1]
│   │   ├── L1  gpaq_activity
│   │   └── L1  "통근·직업 활동량 분석"
│   │
│   ├── L2  "수면·교대근무 평가"                                   [depth=1]
│   │   └── L1  sleep_chronotype
│   │
│   ├── L2  "물질 사용 평가"                                       [depth=1]
│   │   └── L1  audit_c
│   │
│   └── L2  "변화 준비도"                                          [depth=1]
│       ├── L1  motivation_readiness(domain="diet")
│       └── L1  motivation_readiness(domain="activity")
│
├── L3  "risk stratification"                                     [depth=2]
│   ├── L2  "동반질환 스캔"                                        [depth=1]
│   │   ├── L1  "혈압·지질 라벨 리뷰"
│   │   └── L1  "만성콩팥병 스크리닝 (eGFR, UACR 오더)"
│   ├── L1  cvd_risk_calc                                          [depth=0]
│   └── L1  "약물 부작용/금기 점검 (신기능·간기능 기반)"
│
├── L3  "개별 맞춤 관리 계획"                                     [depth=2]
│   │   (intake + stratify 결과에 따라 아래 중 일부만 인스턴스화)
│   ├── L2  "cost-aware 교대근무 식단"                             [depth=1]
│   │   ├── L1  meal_plan_tailored(budget="low", shift="night-rotation")
│   │   └── L1  "편의점 조합 규칙 (샐러드+달걀+두유)"
│   ├── L2  "야간 근무자 운동 루틴"                                [depth=1]
│   │   └── L1  activity_plan_shift(shift="3교대")
│   ├── L2  "약물 치료 시작"                                       [depth=1]
│   │   ├── L1  medication_propose(first_line="metformin")
│   │   └── L1  "환자 설명 + 복약 코칭 (야간 근무 복약 타이밍)"
│   └── L2  "목표 설정 (SMART)"                                    [depth=1]
│       ├── L1  goal_set(target_hba1c="<6.8", horizon="12w")
│       └── L1  goal_set(target_weight="-3kg", horizon="12w")
│
└── L3  "follow-up"                                               [depth=2]
    ├── L2  "안전망 구축"                                          [depth=1]
    │   ├── L1  patient_message_send(template="야간근무 복약 알림", schedule="daily")
    │   └── L1  patient_message_send(template="주 1회 체중 체크인", schedule="weekly")
    └── L2  "재평가 예약"                                          [depth=1]
        ├── L1  followup_schedule(interval="4w", tests=["FBS"])
        └── L1  followup_schedule(interval="12w", tests=["HbA1c", "eGFR", "UACR", "지질"])
```

**핵심 설계 포인트**

- **재귀 깊이는 자유**. 단순한 재진(hospital refill only)은 L2 트리로 끝나고,
  복잡한 신환은 L4까지 성장한다. 고정된 3단계가 아니다.
- **L3 "관리 계획" 은 intake 결과에 따라 다른 L2 자식을 가진다.** 같은 병명이라도
  환자마다 트리 모양이 다르다. Chaeshin이 저장하는 건 "이 프로필의 환자에게는
  이 트리가 통했다"는 사실.
- **각 리프(L1)는 도구 1회 호출 = FHIR 리소스 1개 생성**으로 1:1 대응. 감사
  (audit) 가능.

---

## 4. 시나리오 A — 성공 경로 (12주 뒤 verdict=success)

### T0 — 초진 당일

1. 의료진이 `chaeshin_retrieve(query="신환 T2DM, 야간 3교대, 경제적 제약")` 호출.
   - 유사 케이스 2건 반환. 둘 다 `"개별 맞춤 관리 계획" L3`.
   - 케이스 C(12주 성공, cost-aware + shift-adapted) · 케이스 D(6주 실패, 표준식단 처방).
   - 의료진: C를 참고 트리로 채택, D는 안티패턴으로 회피.

2. `chaeshin_decompose(query=..., tools="dietary_recall_24h,...")` 호출.
   - retain_protocol 받음. 재귀 분해 순서: L4 먼저 저장 → L3 4개 자식 → ...

3. 의료진(실제로는 호스트 AI)이 위 트리 전체를 retain. 각 retain은 **pending**으로 저장:
   ```python
   l4 = chaeshin_retain(
       request="신환 T2DM 초진 — 개별 맞춤 관리 계획 수립",
       layer="L4", depth=3,
       graph={...},
       wait_mode="deadline",
       deadline_seconds=12*7*24*3600,  # 12주
   )
   # outcome_status = "pending"
   # deadline_at = "2026-07-12T..."
   ```
   L3, L2, L1도 parent_case_id 체인으로 연결.
   L1 리프들은 FHIR Observation/CarePlan/MedicationRequest를 실제 EMR에 기록.

4. 환자에게 계획 설명, 처방전 발행, 다음 방문 4주 후로 예약.

### T+4주 — 중간 체크인

- 환자가 외래 재방문. FBS 124, 체중 -1.5kg. 순응도 양호.
- 의료진: 아직 주된 종료점(HbA1c)은 측정 전. **verdict 보류** — 그대로 pending.
- `chaeshin_feedback(case_id=<L2 "cost-aware 교대근무 식단">, feedback="편의점 조합 규칙이 잘 맞는다고 함", feedback_type="correct")` 만 호출. 피드백 카운트 +1.

### T+12주 — 종료점 평가

- HbA1c 6.5%, 체중 -3.2kg, eGFR 안정, UACR 정상.
- 의료진이 모니터 `/hierarchy`에서 환자 케이스 트리 열람 → pending 루트에 **✓ 성공** 클릭.
- 메모: `"HbA1c 7.2→6.5 달성, 편의점 조합 규칙 + 야간 근무 후 근력운동 루틴 둘 다 환자가 끝까지 유지"`
- 이벤트 로그에 `verdict` event 기록. L4 루트부터 자식 L1까지 전부 success로 전환.

### T+14주 — 다른 의료진이 유사 환자 상담

- `chaeshin_retrieve(query="야간 근무 T2DM 신환")` → 이 케이스가 **success**로 최상위 노출.
- `include_children=True`로 L4 전체 트리 로드. 특히 L2 "cost-aware 교대근무 식단"과
  L2 "야간 근무자 운동 루틴"이 재사용 후보.
- 의료진이 신환 프로필에 맞게 **diff만** 수정:
  ```python
  chaeshin_update(case_id=<L2 meal_plan>, patch={
      "problem_features": {"constraints": ["편의점 접근 어려움", "도시락 가능"]},
  })
  ```

---

## 5. 시나리오 B — 중간 상태(pending) 유지

환자가 4주 재방문에 no-show. 전화도 받지 않음.

- 12주 deadline 경과. 케이스는 **pending** 상태 **그대로 유지**.
  - 이게 핵심. 응답 없음 = 실패 아님. 기록되지 않은 성공도 아님.
- `chaeshin_stats.overdue_pending`에 +1 집계. 모니터 `/hierarchy`의 pending 배지가
  overdue 색(진한 호박색)으로 바뀜.
- 의료진은 overdue pending 목록을 주기적으로 리뷰 → "lost to follow-up" 코호트
  식별 → 환자에게 연락 / 지역 보건소 연계 / 케이스 클로즈 결정.
- 결국 의료진이 사회복지팀 상담 기록하고 `chaeshin_verdict(status="failure",
  note="경제적 이유로 이탈, 지역보건소 이관")` 기록. 이는 "계획 자체의 실패"가 아니라
  "이 환자 맥락에서는 이 접근이 못 붙잡았다"는 **맥락 실패** — 다음 의료진에게
  warning으로 노출.

**이 플로우가 가능한 이유는 Chaeshin이 verdict를 추론하지 않기 때문이다.** No-show를
보고 "실패"로 자동 마킹하지 않는다. 임상적 판단 자체가 verdict다.

---

## 6. 시나리오 C — 실패 → 안티패턴 등록

가상의 대안 경로. T0에 의료진이 유사 케이스 검색을 건너뛰고 표준 트리 사용:

- L2 "일반 식단 처방 (한국당뇨협회 표준 식단)" (3끼 균형) 를 그대로 적용.
- 12주 후 HbA1c 7.4%로 악화. 환자 표현: "근무 시간에 차려 먹을 수가 없어요."
- 의료진 `chaeshin_verdict(case_id=<L2 표준식단>, status="failure", note="야간 3교대 환자에게 3끼 균형식은 비현실적, 편의점 조합 대안 필요")`.
- 이 L2는 미래 retrieve에서 `warnings`(유사도 ≥ warning_threshold)로 노출.
- 다음 야간 근무 환자 상담 시 이 실패 케이스가 **경고로 먼저 등장** → 반복 방지.

실패는 지워지지 않는다. 실패는 "이 프로파일에는 쓰지 말라"는 신호로 자산화된다.

---

## 7. Cascading revise — 의료진이 상위 그래프를 재작성하면

**상황**. T+8주 시점, 환자가 "약 복용이 야간 근무 때 놓치기 쉽다"고 호소. 의료진은
계획 자체의 골격을 손본다 — 단순 피드백이 아니라 **L3 "개별 맞춤 관리 계획"의 그래프**
를 수정해야 한다:

```
수정 전:  meal → activity → med → goals
수정 후:  meal → activity → med_simplified → self_monitor → goals
                            └── "med" 노드를 쪼개서 1T + 자가모니터링으로 분리
```

호스트 AI는 단순 update가 아니라 **revise**를 호출한다:

```python
chaeshin_revise(
    case_id=L3_plan_id,
    graph={
        "nodes": [
            {"id": "meal", "tool": "compose"},
            {"id": "activity", "tool": "compose"},
            {"id": "med_simplified", "tool": "compose",
             "note": "1T metformin + 리마인더"},
            {"id": "self_monitor", "tool": "compose",
             "note": "주간 체중/FBS 자가 측정"},
            {"id": "goals", "tool": "compose"},
        ],
        "edges": [
            {"from": "meal", "to": "activity"},
            {"from": "activity", "to": "med_simplified"},
            {"from": "med_simplified", "to": "self_monitor"},
            {"from": "self_monitor", "to": "goals"},
        ],
    },
    reason="환자 복약 순응도 이슈 — 약물 노드 간소화 + 자가 모니터링 추가",
    cascade=True,
)
```

응답:
```json
{
  "added_nodes": ["med_simplified", "self_monitor"],
  "removed_nodes": ["med"],
  "retained_nodes": ["meal", "activity", "goals"],
  "orphaned_children": ["<L2 메트포르민 1차 시작의 case_id>"]
}
```

자동으로 일어나는 일:

1. **고아가 된 L2 "메트포르민 1차 시작"** (parent_node_id="med" → 제거됨)
   - `outcome.status`가 **pending으로 되돌아감**. 의료진이 재검토하기 전에는 신규
     환자 retrieve에서 성공 패턴으로 제안되지 않음.
   - `feedback_log`에 `[cascade] parent node 'med' removed by revise; needs review`
     자동 추가.
   - 모니터 `/hierarchy`에서 rose 배지 **`orphan`** 로 노출 — 놓칠 수 없다.

2. **새 노드 `med_simplified`, `self_monitor`** 가 확장 대상으로 반환.
   - 의료진은 각각 하위 L2 케이스(예: `L2 "간소화 복약 코칭"`)를 새로 retain.
   - `parent_case_id=L3_plan_id`, `parent_node_id="med_simplified"`로 연결.

3. **retained `meal`, `activity`, `goals`** 에 매달려 있던 기존 L2/L1 자식들은
   그대로 유지. 환자가 잘 따라오던 부분은 건드리지 않음.

4. 이벤트 로그에 `revise` 이벤트(added/removed/retained + orphaned_children 전체
   목록)가 추가되어, 누가·언제·왜 수정했는지 감사 가능.

**이게 중요한 이유.** 의료는 계획 수정이 빈번하고, 수정이 어디까지 파급되는지
추적이 안 되면 위험하다. 상위 레이어의 그래프를 바꾼 순간 다운스트림이
"검토 필요" 상태로 자동 표시된다 — 의료진이 놓치는 자식 케이스가 없다.
Chaeshin은 자식을 자동으로 삭제하지 않는다. 의료진의 명시적 결정이 원칙이다.

---

## 8. 재사용 — 유사 환자 내원

6개월 후, 42세 여성, 야간 택시 기사, HbA1c 7.0% 신환.

```python
# 의료진
result = chaeshin_retrieve(
    query="야간 근무 T2DM 신환 초진 관리 계획",
    keywords="야간,3교대,T2DM,신환",
    include_children=True,  # L4 전체 트리 연쇄 로드
    top_k=2,
)
```

- `successes[0]`: 시나리오 A의 L4 트리, similarity 0.82
- `warnings[0]`: 시나리오 C의 표준식단 L2, similarity 0.74 — "이 패턴 피하라"
- `pending[]`: 현재 outcome 미결정 사례들 — 의료진에게 "비슷한 사례 아직 결정 안 남" 신호

의료진은 성공 트리를 베이스로 채택. 차이점만 diff로 반영:
- 이 환자는 여성 → 심혈관 위험도 재계산
- 이 환자는 대시보드 앱 사용 불가(피처폰) → `patient_message_send` 템플릿을 SMS로 교체

```python
chaeshin_update(
    case_id=<L1 patient_message_send>,
    patch={"solution": {"tool_graph": {"nodes": [{"id":"n1","tool":"patient_message_send","params_hint":{"channel":"sms"}}]}}},
)
```

변경은 diff로 이벤트 로그에 남는다. 6개월 후 또 다른 환자가 오면, 이 두 케이스의
공통점이 점점 "검증된 야간 근무자 T2DM 프로토콜"이 되어간다. 이게 Chaeshin이
"의료진 개인 경험"을 "팀 자산"으로 바꾸는 방식이다.

---

## 9. FHIR R5 리소스 매핑 부록

Chaeshin 케이스 트리의 각 레벨이 FHIR 리소스로 어떻게 떨어지는지:

| Chaeshin | FHIR R5 | 비고 |
|----------|---------|------|
| L4 "관리 계획" root case | `CarePlan` (category=assess-plan, intent=plan) | `CarePlan.activity`에 각 L3 ref |
| L3 "lifestyle intake" | `QuestionnaireResponse` + 여러 `Observation` | 문진 세트 결과 |
| L3 "risk stratification" | `RiskAssessment` | ASCVD 결과 포함 |
| L2 "약물 치료 시작" | `MedicationRequest` | Encounter와 연결 |
| L2 "목표 설정" | `Goal` (lifecycleStatus=planned → active) | verdict=success 시 `achievementStatus=achieved` |
| L1 leaf (도구 호출 1회) | `Observation` / `ServiceRequest` / `Communication` | 도구별 매핑 |
| `outcome.status="pending"` | `Goal.lifecycleStatus="active"` + `CarePlan.status="active"` | 아직 평가 전 |
| `outcome.status="success"` | `Goal.achievementStatus="achieved"` | verdict_at → `Goal.statusReason.text` |
| `outcome.status="failure"` | `Goal.achievementStatus="not-achieved"` | error_reason → statusReason |
| `metadata.deadline_at` | `Goal.target.dueDate` | 12주 타깃 등 |
| `events` 테이블 | `AuditEvent` 또는 `Provenance` | 누가·언제·무엇을 호출했는지 |

**R4 다운그레이드** — `R5 Goal.achievementStatus` → `R4 Goal.outcomeReference` +
`outcomeCode`로 변환. `RiskAssessment`는 R4/R5 거의 동일. 자세한 변환 표는
health_agent의 `fhir/downgrade.py` 참조.

---

## 부록 — 실행 가능한 데모

이 시나리오를 코드로 재현하는 최소 데모는 [`demo.py`](demo.py)에 있다. 실제 EMR
없이 Chaeshin 저장소 동작만 보여준다:

```bash
uv run python -m examples.medical_intake.demo
```

데모가 보여주는 것:
1. L4→L1 전체 트리를 pending으로 저장
2. 유사 쿼리로 retrieve → pending/successes/failures 분리 확인
3. 12주 후 시점 시뮬레이션 → verdict=success 기록
4. diff 기반 update로 다음 환자에게 적용

---

## 맺음말

Chaeshin이 의료 도메인에서 의미 있는 이유는 세 가지다:

1. **Pending을 일급 상태로 다룬다** — 의료는 결과 확인까지 시간이 걸린다. 추측하지
   않는 설계가 곧 안전한 설계다.
2. **재귀 깊이 자유** — 환자마다 트리 모양이 다르다. 고정 3단계가 강제하는 억지
   fit은 의료 현실과 맞지 않는다.
3. **실패를 자산화한다** — 같은 환자 프로파일에서의 실패는 다음 의료진에게 경고로
   노출된다. 조직 학습이 자동으로 쌓인다.

이 세 가지는 Chaeshin v3의 핵심 설계 결정과 1:1로 대응된다: tri-state outcome,
arbitrary-depth decomposition, `retrieve_with_warnings`. 의료 도메인 플랫폼이
Chaeshin 위에서 자연스럽게 성장할 수 있는 이유다.
