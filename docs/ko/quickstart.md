# 빠른 시작

[English](../quickstart.md)

2분 안에 채신을 실행해봅니다.

## 1. 설치

```bash
pip install chaeshin
```

또는 [uv](https://docs.astral.sh/uv/)로:

```bash
uv pip install chaeshin
```

소스에서 설치:

```bash
git clone https://github.com/GEOHYEON/chaeshin.git
cd chaeshin
uv sync --all-extras        # 권장
# 또는: pip install -e ".[dev]"
```

## 2. 요리사 에이전트 데모 실행

```bash
python -m examples.cooking.chef_agent
```

김치찌개 레시피를 예시로 CBR의 전체 사이클(Retrieve → Execute → Retain)을 실행합니다.

### 실행 결과

```
============================================================
  Step 1: CBR 케이스 저장소 로드
============================================================

  → 저장된 케이스: 5개
  → - recipe_kimchi_stew_001: 김치찌개 만들어줘

============================================================
  Step 3: CBR — 유사 케이스 검색
============================================================

  → [0.850] recipe_kimchi_stew_001: 김치찌개 만들어줘
  → ✅ 최적 케이스 선택: recipe_kimchi_stew_001

============================================================
  Step 5: 실행
============================================================

  → 🍳 [알레르기 체크] 시작
  → ✅ [알레르기 체크] 완료
  → 🍳 [재료 확인] 시작
  → ✅ [재료 확인] 완료
  → 🍳 [썰기] 시작
  ...
  → ✅ [담기] 완료 — 김치찌개 2인분 완성

============================================================
  🎉 완료!
============================================================
```

저장된 5개 케이스 중 "김치찌개 2인분 해줘"와 가장 유사한 케이스를 찾아서, 각 도구 노드를 순서대로 실행하고, 성공하면 결과를 다시 저장합니다.

## 3. 흐름 이해하기

데모는 6단계로 진행됩니다:

```
사용자 요청 → Retrieve (유사 케이스 검색)
           → Inspect (Tool Graph 확인)
           → Execute (노드별 도구 실행)
           → Retain (성공 시 저장)
```

**Retrieve**: `CaseStore`가 키워드 겹침과 유사도 점수로 요청과 저장된 케이스를 비교합니다. 가장 잘 맞는 Tool Graph를 반환합니다.

**Execute**: `GraphExecutor`가 그래프를 노드 단위로 실행합니다. 각 노드는 도구 함수를 호출합니다. 엣지가 흐름을 정의합니다 — 조건("싱거우면 → 다시 끓이기")과 병렬 그룹 포함.

**Retain**: 실행이 성공하고 만족도 기준을 넘으면, 새 케이스가 저장소에 저장되어 나중에 재사용됩니다.

## 4. 코드 살펴보기

| 파일 | 역할 |
|------|------|
| `examples/cooking/cases.json` | 5개 CBR 케이스 (김치찌개, 된장찌개, 복구 시나리오) |
| `examples/cooking/tools.py` | 모의 요리 도구 (썰기, 끓이기, 간보기 등) |
| `examples/cooking/chef_agent.py` | 규칙 기반 데모 스크립트 |
| `examples/cooking/chef_agent_llm.py` | LLM + VectorDB 데모 스크립트 |
| `examples/cooking/app.py` | Gradio 웹 UI 데모 |
| `chaeshin/case_store.py` | CBR 케이스 저장 및 검색 |
| `chaeshin/graph_executor.py` | Tool Graph 실행 엔진 |
| `chaeshin/planner.py` | LLM 기반 그래프 생성/적응/리플래닝 |
| `chaeshin/integrations/openai.py` | OpenAI LLM + 임베딩 어댑터 |
| `chaeshin/integrations/chroma.py` | ChromaDB 벡터 케이스 저장소 |
| `chaeshin/schema.py` | 데이터 모델 (Case, ToolGraph, Edge, Node) |

## 5. LLM + VectorDB로 실행

OpenAI LLM과 ChromaDB 벡터 검색을 사용하는 전체 기능 데모:

```bash
cp .env.example .env         # OPENAI_API_KEY 입력
uv run python -m examples.cooking.chef_agent_llm
```

이 데모에서는:

- OpenAI 임베딩으로 케이스를 ChromaDB에 저장
- 키워드가 아닌 벡터 유사도로 케이스 검색
- LLM이 검색된 그래프를 현재 상황에 맞게 적응
- 예상치 못한 상황에서 LLM이 diff 기반으로 그래프 수정
- 성공한 결과를 ChromaDB에 저장해 다음에 재활용

옵션:

```bash
# 새 요리 시나리오 — LLM이 처음부터 그래프 생성
uv run python -m examples.cooking.chef_agent_llm --scenario new

# 두 시나리오 모두 실행
uv run python -m examples.cooking.chef_agent_llm --scenario both

# ChromaDB 데이터 초기화
uv run python -m examples.cooking.chef_agent_llm --reset
```

## 6. 웹 UI 데모 (Gradio)

웹 브라우저에서 인터랙티브하게 체험:

```bash
cp .env.example .env         # OPENAI_API_KEY 입력
uv run python -m examples.cooking.app
```

Gradio 웹 앱에서:

- 자연어로 요리 요청 입력
- CBR 파이프라인(Retrieve → Adapt → Execute → Retain) 단계별 시각화
- 생성된 Tool Graph 확인
- 실시간 실행 현황 추적
- 프리셋 예시 (김치찌개, 된장찌개, 치즈 오믈렛 등)

옵션:

```bash
# 포트 변경
uv run python -m examples.cooking.app --port 8080

# 공개 공유 링크 생성
uv run python -m examples.cooking.app --share

# ChromaDB 데이터 초기화 후 실행
uv run python -m examples.cooking.app --reset
```

## 7. 다음 단계

**나만의 케이스 추가**: `examples/cooking/cases.json`을 편집해서 새 레시피를 추가하세요. 기존 구조를 따라 노드(도구), 엣지(흐름), 문제 특성(키워드)을 정의합니다.

**다른 도메인 만들기**: 채신은 도메인에 독립적입니다. 요리 도구 대신 자신만의 도구(API 호출, DB 쿼리, 파일 작업)를 넣고 케이스를 만드세요.

**테스트 실행**:

```bash
make test
```

---

*아키텍처와 핵심 개념은 [README](../../README.md)를 참고하세요.*
