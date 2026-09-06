# Vision — 채신(Chaeshin)의 비전

## 교자채신 (敎子採薪)

> 자식에게 나무를 주지 말고, 나무 모으는 법을 가르쳐라.

이것이 Chaeshin의 핵심 철학입니다.

## 문제 인식

현재 LLM 에이전트의 도구 사용 방식은 두 극단에 있습니다.

**자유형 (ReAct)**: LLM이 매번 어떤 도구를 쓸지 즉석에서 결정합니다. 레시피 없이 즉흥 요리하는 것과 같습니다. 유연하지만, 중요한 단계를 건너뛰거나 잘못된 순서로 실행할 수 있습니다.

**고정형 (LangGraph 등)**: 개발자가 실행 순서를 코드에 박아넣습니다. 레시피를 코드로 하드코딩하는 것과 같습니다. 안정적이지만, 새로운 상황마다 코드를 수정해야 합니다.

## Chaeshin의 접근

Chaeshin은 세 번째 길을 제안합니다:

**ReAct를 대체하지 않고 경험에서 배운다.** 실행 세부 사항은 L1 ToolGraph로,
더 높은 재사용 구조는 바로 아래 Layer Case 약 5~7개를 묶는 L2+ Procedure로
저장합니다. 비슷한 상황이 오면 모든 Layer를 함께 검색하고 크기가 제한된 근거를
LLM Context로 제공합니다. Case-Based Reasoning(CBR)의 Retrieve → Reuse → Revise
→ Retain 사이클을 LLM Tool Calling에 적용한 것입니다.

이것은 "물고기를 주는 것"(고정 파이프라인)도, "맨손으로 잡게 하는 것"(메모리
없는 ReAct)도 아닙니다. **"낚시하는 법을 가르치는 것"**입니다. 채신은 실행
계획을 확정해 주지 않습니다. Host ReAct가 검색된 Procedure/ToolGraph Context와
현재 Situation을 참고하고, Observation을 받을 때마다 다음 Tool 하나를 직접
선택합니다.

## 기술적 차별점

1. **ToolGraph Base + Procedure 계층**: L1은 하나 이상의 실행 가능한 Tool
   node를 가진 ToolGraph입니다. L2 이상은 바로 아래 Layer Case 약 5~7개로
   구성된 Procedure이며, ProcedureStep anchor를 따라가면 L1에 도달합니다.

2. **모든 Layer를 함께 보는 Situation-aware 검색**: L1부터 LN까지 하나의 후보
   공간에 들어갑니다. ProblemFeatures, 현재 상태, outcome, provenance, ontology
   관계로 Context를 구성하며 Layer를 사전 routing gate로 쓰지 않습니다.

3. **Observation 기반 ReAct 활용**: Tool 결과가 나오면 Situation을 다시
   파악하고, 필요하면 채신을 재검색한 뒤 ReAct가 다음 Tool을 선택합니다. 채신은
   그 앞에서 적용 가능성 분류, Planner, 그래프 실행을 담당하지 않습니다.

4. **버전 및 거버넌스**: 구조 변경은 추적 가능한 revision을 만들고, outcome,
   provenance, validity, review state, Tool schema compatibility를 분리해 관리합니다.

## 영감을 준 연구

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943)
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453)
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291)
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1)
- [HTN Plan Repair Algorithms (2025)](https://arxiv.org/abs/2504.16209)

## 우리가 믿는 것

- 에이전트는 경험에서 배워야 합니다
- 절차 근거는 구조화되고 provenance와 연결되어야 합니다
- ReAct는 메모리를 Context로 참고하되 저장된 계획에 통제권을 넘기지 않아야 합니다
- Situation이나 최신 Observation이 달라지면 Tool 선택도 달라져야 합니다
- 좋은 프레임워크는 도메인에 독립적이어야 합니다

Chaeshin은 요리사가 될 수도, 의사가 될 수도, 코딩 에이전트가 될 수도 있습니다.
도구와 케이스만 바꾸면 됩니다.

---

*"에이전트에게 계획을 주면 하나를 풀고, 계획을 찾는 법을 가르치면 모두를 푼다."*
