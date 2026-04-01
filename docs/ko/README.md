# 채신 (Chaeshin) 採薪

> **"에이전트에게 계획을 주면 하나를 풀고, 계획을 찾는 법을 가르치면 모두를 푼다."**

**채신**은 LLM 도구 호출(Tool Calling)을 위한 Case-Based Reasoning(CBR) 프레임워크입니다. 과거에 성공한 도구 실행 그래프를 저장하고, 비슷한 문제가 오면 꺼내 쓰고, 상황에 맞게 고쳐서 실행합니다.

**v2**에서는 계층적 태스크 분해, 레이어별 실행, 피드백 기반 학습을 지원하는 멀티 에이전트 아키텍처가 추가되었습니다.

교자채신(敎子採薪) — *나무를 주지 말고, 나무 모으는 법을 가르쳐라.*

[English](../../README.md) | [中文](../zh/README.md) | [日本語](../ja/README.md) | [Español](../es/README.md) | [Français](../fr/README.md) | [Deutsch](../de/README.md)

---

## 설치

```bash
pip install chaeshin
```

또는 [uv](https://docs.astral.sh/uv/) (권장):

```bash
uv pip install chaeshin
```

끝. 이제 에이전트에 연결하세요:

## 에이전트 연결 — 한 줄 셋업

두 플랫폼 모두 `~/.chaeshin/cases.json`을 공유합니다. Claude Code에서 쌓인 케이스를 OpenClaw에서 쓸 수 있고, 그 반대도 가능합니다.

<p align="center">
  <img src="../../assets/integrations.ko.svg" alt="채신 연동 구조 — Claude Code & OpenClaw" width="820"/>
</p>

### Claude Code

```bash
chaeshin setup claude-code
```

이 한 줄이면 MCP 서버 등록과 자동학습 규칙(`CLAUDE.md`) 설치가 동시에 됩니다. Claude가 멀티스텝 작업 전에 과거 패턴을 자동으로 찾고, 완료 후 새 패턴을 자동으로 저장합니다.

5개 도구가 추가됩니다:

| 도구 | 설명 |
|------|------|
| `chaeshin_retrieve` | 유사 케이스 검색 — 성공 케이스 + 안티패턴 경고. v2: 계층 연쇄 로드 (`include_children`/`include_parent`) |
| `chaeshin_retain` | 실행 그래프 저장 (성공/실패 모두). v2: 레이어/부모-자식/난이도 태깅 |
| `chaeshin_feedback` | **(v2 신규)** 유저 피드백 기록 — ESCALATE/MODIFY/SIMPLIFY/CORRECT/REJECT |
| `chaeshin_decompose` | **(v2 신규)** 질문을 계층 태스크 트리로 분해 + 난이도 산출 + Chaeshin 조회 판단 |
| `chaeshin_stats` | 케이스 저장소 통계 |

<details>
<summary><code>uvx</code>로 (글로벌 설치 없이)</summary>

```bash
uvx chaeshin setup claude-code --uvx
```
</details>

<details>
<summary>수동 설정 (<code>claude</code> CLI가 없는 경우)</summary>

`~/.claude.json`에 추가:

```json
{
  "mcpServers": {
    "chaeshin": {
      "command": "uv",
      "args": ["tool", "run", "chaeshin-mcp"]
    }
  }
}
```
</details>

### OpenClaw

```bash
chaeshin setup openclaw
```

`~/.openclaw/workspace/skills/chaeshin/`에 `SKILL.md`가 설치됩니다. OpenClaw 에이전트가 바로 Tool Graph 메모리를 사용하기 시작합니다.

### Claude Desktop

```bash
chaeshin setup claude-desktop --openai-key sk-...
```

OS를 자동 감지하고, `claude_desktop_config.json`에 설정을 쓰고, 벡터 임베딩을 위한 `OPENAI_API_KEY`도 함께 세팅합니다. Claude Desktop을 재시작하면 끝.

### 독립 사용 (any agent)

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="슬랙에 PR 요약 보내줘"))
if results:
    graph = results[0][0].solution.tool_graph
```

---

## v2 — 멀티 에이전트 아키텍처

### 전체 흐름

```
유저 질문
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│               OrchestratorAgent (대화 루프)               │
│                                                         │
│  1) 난이도 판단 (Chaeshin 기반 + LLM fallback)            │
│  2) 쉬우면 → 직접 그래프 생성 + 실행                      │
│  3) 어려우면 → Decomposer 서브에이전트 spawn               │
│  4) 피드백 → Reflection 서브에이전트 spawn                 │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
    Decomposer    Executor    Reflection
     (분해)        (실행)      (피드백 반영)
```

### 에이전트별 역할

**OrchestratorAgent** — 총괄 대화 루프. 유저 질문을 받아서 난이도 판단 후 적절한 서브에이전트에 위임합니다. 쉬운 질문(tool call 1~2개)은 직접 처리하고, 복잡한 질문만 Decomposer→Executor 파이프라인으로 넘깁니다.

**DecomposerAgent** — 계층적 태스크 분해. 질문을 3~5개 하위 태스크로 나누고, 각 태스크가 tool call 하나로 실행 가능할 때까지 재귀적으로 분해합니다. 분해 깊이가 곧 난이도(difficulty)입니다.

**ExecutorAgent** — 레이어별 실행. 분해 트리의 최하위(L1)부터 tool call을 실행하고, 레이어가 끝날 때마다 유저에게 체크포인트를 보고합니다.

**ReflectionAgent** — 피드백 반영. 유저 피드백을 LLM이 해석하여 그래프를 변환합니다:

| 유형 | 예시 | 동작 |
|------|------|------|
| ESCALATE | "이건 더 복잡해" | 기존 그래프를 한 레벨 아래로 밀고, 새 상위 레이어 생성 |
| MODIFY | "순서 바꿔" | 노드/엣지 수정 |
| SIMPLIFY | "한번에 해도 돼" | 하위 레이어를 상위로 병합 |
| CORRECT | "이 툴 대신 저걸 써" | tool 노드 교체 |
| REJECT | "이건 안 해도 돼" | 노드 제거 + 엣지 재연결 |

### SubagentManager

Orchestrator는 `SubagentManager`를 통해 서브에이전트를 관리합니다:

```python
from chaeshin.agents import OrchestratorAgent

orch = OrchestratorAgent(llm_fn=my_llm, tools=my_tools, case_store=store)

# 단일 질문 처리 (AsyncGenerator)
async for event in orch.run("위클리 미팅을 준비해줘"):
    print(event)

# 인터랙티브 대화 루프
await orch.interactive_loop(input_fn=..., output_fn=...)

# 피드백 처리
async for event in orch.handle_feedback("팀별로 나눠서 수집해야 해"):
    print(event)
```

### Chaeshin 검색 트리거

모든 질문에 과거 기억을 뒤지지 않습니다. 두 가지 조건 중 하나를 만족할 때만 Chaeshin을 조회합니다:

| 조건 | 설명 |
|------|------|
| `difficulty ≥ 2` | 분해가 2단계 이상 필요한 복잡한 질문 |
| `feedback_count ≥ 3` | 해당 영역에 유저 피드백이 3회 이상 누적된 영역 |

### 레이어 구조

| 레이어 | 하위 노드 수 | 역할 |
|--------|-------------|------|
| L3 (전략) | 3~5개 | 전체 방향 설정 |
| L2 (패턴) | 5~7개 | 실행 패턴 구성 |
| L1 (실행) | 7~15개 tool call | 실제 도구 호출 |

---

## 모니터 — 비주얼 Tool Graph 에디터

<p align="center">
  <img src="../../assets/tool-graph.ko.svg" alt="Tool Graph 예시 — 김치찌개" width="720"/>
</p>

채신은 Next.js + React Flow 기반의 웹 모니터(`chaeshin-monitor/`)를 포함합니다. 케이스 메모리에 저장된 Tool Graph를 시각적으로 조회·생성·편집할 수 있습니다.

```bash
cd chaeshin-monitor
pnpm install && pnpm dev
```

---

## 왜 채신인가?

대부분의 LLM 에이전트는 도구 호출을 즉흥적으로 하거나(ReAct), 개발자가 짜둔 고정 파이프라인을 따릅니다. 둘 다 한계가 있습니다.

- **즉흥형**: LLM이 단계를 빼먹거나, 순서를 틀리거나, 같은 실수를 반복합니다.
- **고정형**: 새로운 상황마다 코드를 고쳐야 합니다. 확장이 어렵습니다.

채신은 다른 접근을 합니다: **잘 됐던 걸 기억하고, 다시 써먹는 것.**

요청이 들어오면 비슷한 과거 케이스를 찾고, 그때 성공했던 도구 실행 그래프를 꺼내서, 필요하면 수정하고, 실행한 뒤, 성공하면 다시 저장합니다. 이것이 [Case-Based Reasoning](https://ko.wikipedia.org/wiki/%EC%82%AC%EB%A1%80_%EA%B8%B0%EB%B0%98_%EC%B6%94%EB%A1%A0)의 **Retrieve → Reuse → Revise → Retain** 사이클입니다.

## 일반 LLM vs 채신

<p align="center">
  <img src="../../assets/comparison.ko.svg" alt="일반 LLM vs 채신 — 치즈토스트 비교" width="820"/>
</p>

## 작동 방식

### 자동학습

`chaeshin setup claude-code` 실행 후, Claude가 자동으로:

1. **작업 전** → `chaeshin_retrieve`를 호출하여 과거 패턴 확인
2. **작업 후** → `chaeshin_retain`을 호출하여 실행 그래프 저장
3. **실패 시** → 실패 패턴도 사유와 함께 저장하여 재발 방지

retrieve/retain을 직접 부르지 않아도 됩니다. **쓰면 쓸수록 똑똑해집니다.**

```
Day 1:   모든 작업을 처음부터 즉흥적으로 처리
Day 7:   20개 케이스 축적 — 반복 패턴 재사용 시작
Day 30:  100+ 케이스 — 검증된 패턴 우선, 실패 패턴 자동 회피
```

### Tool Graph — 실행 설계도

도구 호출을 **그래프 구조**로 표현합니다. DAG가 아닌 일반 그래프라서 **루프**도 가능합니다. 노드는 도구 호출, 엣지는 실행 순서와 조건을 나타냅니다.

### 불변 그래프 + 가변 컨텍스트

Tool Graph는 실행 중 바뀌지 않습니다. 바뀌는 건 **실행 컨텍스트**(커서 위치, 노드 상태, 출력값)뿐입니다. 예상치 못한 상황이 발생해서 매칭되는 엣지가 없으면, 그때만 LLM에게 그래프 수정을 요청합니다. 수정은 diff 형태(노드/엣지 추가·삭제)로 이루어집니다.

### 예상치 못한 상황이 발생하면?

실행 중 항상 계획대로 되진 않습니다. 채신은 **diff 기반 리플래닝**으로 이를 처리합니다 — 매칭되는 엣지가 없을 때만 LLM이 개입합니다:

<p align="center">
  <img src="../../assets/replan-scenarios.ko.svg" alt="리플래닝 시나리오 — 전화, 알레르기, 재료 부족" width="780"/>
</p>

정상 실행 중에는 그래프가 불변입니다. **매칭되는 엣지가 없는 예외**가 발생했을 때만 LLM이 개입해서 최소한의 diff로 그래프를 수정합니다. 전체 재생성이 아니라 변경분만 적용합니다.

## 빠른 시작 — 김치찌개 요리사

**규칙 기반 데모** (API 키 불필요):

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras
uv run python -m examples.cooking.chef_agent
```

**LLM + VectorDB 데모** (OpenAI + ChromaDB):

```bash
cp .env.example .env         # OPENAI_API_KEY 입력
uv run python -m examples.cooking.chef_agent_llm
```

**웹 UI 데모** (Gradio):

```bash
cp .env.example .env         # OPENAI_API_KEY 입력
uv run python -m examples.cooking.app
```

## 아키텍처

<p align="center">
  <img src="../../assets/architecture.ko.svg" alt="채신 아키텍처" width="600"/>
</p>

## 프로젝트 구조

```
chaeshin/
├── agents/                 # v2: 멀티 에이전트 런타임
│   ├── base.py             #   BaseAgent (AsyncGenerator) + SubagentManager
│   ├── orchestrator.py     #   대화 루프 + 서브에이전트 디스패치
│   ├── decomposer.py       #   계층적 태스크 분해
│   ├── executor_agent.py   #   레이어별 실행 + 체크포인트
│   └── reflection.py       #   피드백 → 그래프 변환 (ESCALATE/MODIFY/SIMPLIFY/CORRECT/REJECT)
├── cli/                    # chaeshin setup claude-code / claude-desktop / openclaw
│   └── main.py
├── integrations/
│   ├── claude_code/        # MCP 서버 (FastMCP) + CLAUDE.md 템플릿
│   │   ├── mcp_server.py   #   5개 도구: retrieve, retain, feedback, decompose, stats
│   │   └── CLAUDE.md
│   ├── openclaw/           # SKILL.md + 브리지 CLI (subprocess)
│   │   ├── SKILL.md
│   │   └── bridge.py
│   ├── openai.py           # LLM + 임베딩 어댑터
│   └── chroma.py           # VectorDB 케이스 저장소
├── schema.py               # 코어 데이터 타입 (v2: 계층/피드백 필드 포함)
├── case_store.py           # CBR 검색 / 저장 (v2: 계층 탐색 + 피드백 가중치)
├── graph_executor.py       # Tool Graph 실행 엔진 (v2: 레이어별 실행)
└── planner.py              # LLM 그래프 생성 / 적응 / 리플래닝 (v2: 계층 분해 + TaskTree)
chaeshin-monitor/           # Next.js 웹 UI — 비주얼 그래프 빌더 & 케이스 뷰어
```

## 관련 연구

채신은 다음 연구들에서 영감을 받았습니다:

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM 통합 서베이
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — CBR 기반 데이터 사이언스 에이전트
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — 스킬 라이브러리 기반 경험 학습
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1) — 그래프 기반 도구 병렬 실행
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — 계층적 플랜 수리

**기존 연구와 다른 점:** 채신은 Tool Graph를 CBR 케이스로 저장하고, 루프를 지원하는 일반 그래프를 사용하며, 전체 재생성 대신 diff 기반으로 그래프를 수정하고, 코드가 정상 흐름을 처리하되 LLM은 예외 상황에만 개입하는 하이브리드 실행 방식을 결합합니다. v2에서는 계층적 분해(HTN), 피드백 기반 학습, 멀티 에이전트 오케스트레이션이 추가되었습니다.

## 라이선스

MIT License — [LICENSE](../../LICENSE) 참고

---

*敎子採薪 — 나무를 주지 말고, 나무 모으는 법을 가르쳐라.*
