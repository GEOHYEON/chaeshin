# 채신 (Chaeshin) 採薪

> **"에이전트에게 계획을 주면 하나를 풀고, 계획을 찾는 법을 가르치면 모두를 푼다."**

**채신**은 LLM 도구 호출(Tool Calling)을 위한 Case-Based Reasoning(CBR) 프레임워크입니다. 과거에 성공한 도구 실행 그래프를 저장하고, 비슷한 문제가 오면 꺼내 쓰고, 상황에 맞게 고쳐서 실행합니다.

교자채신(敎子採薪) — *나무를 주지 말고, 나무 모으는 법을 가르쳐라.*

[English](../../README.md)

---

## 연동 — 한 줄 셋업

두 플랫폼 모두 `~/.chaeshin/cases.json`을 공유합니다 — Claude Code에서 쌓인 케이스를 OpenClaw에서 쓸 수 있고, 그 반대도 가능합니다.

<p align="center">
  <img src="../../assets/integrations.ko.svg" alt="채신 연동 구조 — Claude Code & OpenClaw" width="820"/>
</p>

### Claude Code

```bash
pip install chaeshin && chaeshin setup claude-code
```

Chaeshin [MCP](https://modelcontextprotocol.io/) 서버가 Claude Code에 등록됩니다. 4개 도구가 추가됩니다:

| 도구 | 설명 |
|------|------|
| `chaeshin_retrieve` | 유사 케이스 검색 — 성공 케이스 + 안티패턴 경고 |
| `chaeshin_retain` | 실행 그래프 저장 (성공/실패 모두) |
| `chaeshin_anticipate` | 현재 컨텍스트 기반 선제 제안 |
| `chaeshin_stats` | 케이스 저장소 통계 |

멀티 스텝 작업 전에 유사한 패턴을 검색합니다. 성공 케이스와 함께 과거 실패한 **안티패턴 경고**도 반환합니다. 완료 후 실행 그래프를 저장하며, 실패한 실행도 사유와 함께 저장해서 같은 실수를 반복하지 않습니다.

<details>
<summary>수동 설정 (<code>claude</code> CLI가 없는 경우)</summary>

`~/.claude.json`에 추가:

```json
{
  "mcpServers": {
    "chaeshin": {
      "command": "python",
      "args": ["-m", "chaeshin.integrations.claude_code.mcp_server"]
    }
  }
}
```
</details>

### OpenClaw

```bash
pip install chaeshin && chaeshin setup openclaw
```

`~/.openclaw/workspace/skills/chaeshin/`에 `SKILL.md`가 설치됩니다. OpenClaw 에이전트가 Tool Graph 메모리를 사용하기 시작합니다.

브리지 CLI로 JSON 기반 검색/저장이 가능합니다:

```bash
# 유사 케이스 검색
python -m chaeshin.integrations.openclaw.bridge retrieve "스테이징 배포"

# 성공 패턴 저장
python -m chaeshin.integrations.openclaw.bridge retain \
    --request "스테이징 배포" \
    --graph '{"nodes":[...],"edges":[...]}'

# 통계 확인
python -m chaeshin.integrations.openclaw.bridge stats
```

### 독립 사용 (any agent)

```python
from chaeshin import CaseStore, ProblemFeatures

store = CaseStore()
store.load_json(open("cases.json").read())

results = store.retrieve(ProblemFeatures(request="슬랙에 PR 요약 보내줘"))
if results:
    graph = results[0][0].solution.tool_graph
```

### 프로젝트 구조

```
chaeshin/
├── cli/                    # chaeshin setup claude-code / openclaw
│   └── main.py
├── integrations/
│   ├── claude_code/        # MCP 서버 (stdio 프로토콜)
│   │   └── mcp_server.py
│   ├── openclaw/           # SKILL.md + 브리지 CLI (subprocess)
│   │   ├── SKILL.md
│   │   └── bridge.py
│   ├── openai.py           # LLM + 임베딩 어댑터
│   └── chroma.py           # VectorDB 케이스 저장소
├── schema.py               # 코어 데이터 타입
├── case_store.py            # CBR 검색 / 저장
├── graph_executor.py        # Tool Graph 실행 엔진
└── planner.py               # LLM 기반 그래프 생성 / 적응 / 리플래닝
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

## 핵심 개념

### Tool Graph — 실행 설계도

도구 호출을 **그래프 구조**로 표현합니다. DAG가 아닌 일반 그래프라서 **루프**도 가능합니다.

<p align="center">
  <img src="../../assets/tool-graph.ko.svg" alt="Tool Graph 예시 — 김치찌개" width="720"/>
</p>

### CBR Case — 문제-해법-결과-메타

각 케이스는 `(problem, solution, outcome, metadata)` 튜플입니다:

```python
Case(
    problem_features=ProblemFeatures(
        request="김치찌개 만들어줘",
        category="찌개류",
        keywords=["김치", "찌개", "묵은지"],
    ),
    solution=Solution(
        tool_graph=ToolGraph(nodes=[...], edges=[...])
    ),
    outcome=Outcome(success=True, user_satisfaction=0.90),
    metadata=CaseMetadata(used_count=25, avg_satisfaction=0.88),
)
```

### 불변 그래프 + 가변 컨텍스트

Tool Graph는 실행 중 바뀌지 않습니다. 바뀌는 건 **실행 컨텍스트**(커서 위치, 노드 상태, 출력값)뿐입니다. 예상치 못한 상황이 발생해서 매칭되는 엣지가 없으면, 그때만 LLM에게 그래프 수정을 요청합니다. 수정은 diff 형태(노드/엣지 추가·삭제)로 이루어집니다.

### 예상치 못한 상황이 발생하면?

실행 중 항상 계획대로 되진 않습니다. 채신은 **diff 기반 리플래닝**으로 이를 처리합니다 — 매칭되는 엣지가 없을 때만 LLM이 개입합니다:

<p align="center">
  <img src="../../assets/replan-scenarios.ko.svg" alt="리플래닝 시나리오 — 전화, 알레르기, 재료 부족" width="780"/>
</p>

핵심 원리: 정상 실행 중에는 그래프가 불변입니다. **매칭되는 엣지가 없는 예외**가 발생했을 때만 LLM이 개입해서 최소한의 diff로 그래프를 수정합니다. 전체 재생성이 아니라 변경분만 적용합니다.

## 설치

```bash
pip install chaeshin
```

또는 [uv](https://docs.astral.sh/uv/)로:

```bash
uv pip install chaeshin
```

소스에서:

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # 권장
# 또는: pip install -e ".[dev]"
```

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

브라우저에서 요리 요청을 입력하면 CBR 파이프라인이 단계별로 실행되는 것을 볼 수 있습니다.

```python
from chaeshin import CaseStore, GraphExecutor, ProblemFeatures

# 1. CBR 케이스 저장소 로드
store = CaseStore()
store.load_json(open("cases.json").read())

# 2. 유사 케이스 검색
problem = ProblemFeatures(
    request="김치찌개 2인분 해줘",
    category="찌개류",
    keywords=["김치", "찌개"],
)
case = store.retrieve_best(problem)

# 3. Tool Graph 실행
executor = GraphExecutor(tools=COOKING_TOOLS)
ctx = await executor.execute(case.solution.tool_graph)

# 4. 성공하면 저장
store.retain_if_successful(new_case)
```

## 아키텍처

<p align="center">
  <img src="../../assets/architecture.ko.svg" alt="채신 아키텍처" width="600"/>
</p>

## 관련 연구

채신은 다음 연구들에서 영감을 받았습니다:

- [Case-Based Reasoning for LLM Agents (2025)](https://arxiv.org/abs/2504.06943) — CBR + LLM 통합 서베이
- [DS-Agent (ICML 2024)](https://arxiv.org/abs/2402.17453) — CBR 기반 데이터 사이언스 에이전트
- [Voyager (NeurIPS 2023)](https://arxiv.org/abs/2305.16291) — 스킬 라이브러리 기반 경험 학습
- [GAP: Graph-based Agent Planning (2025)](https://arxiv.org/html/2510.25320v1) — 그래프 기반 도구 병렬 실행
- [HTN Plan Repair (2025)](https://arxiv.org/abs/2504.16209) — 계층적 플랜 수리

**기존 연구와 다른 점:** 채신은 Tool Graph를 CBR 케이스로 저장하고, 루프를 지원하는 일반 그래프를 사용하며, 전체 재생성 대신 diff 기반으로 그래프를 수정하고, 코드가 정상 흐름을 처리하되 LLM은 예외 상황에만 개입하는 하이브리드 실행 방식을 결합합니다.

## 라이선스

MIT License — [LICENSE](../../LICENSE) 참고

---

*敎子採薪 — 나무를 주지 말고, 나무 모으는 법을 가르쳐라.*
