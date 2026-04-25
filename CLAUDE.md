# Chaeshin Project — Claude Code Rules

**공통 규칙은 bananatouch-harness를 정본으로 따른다.**
공용 규칙 수정은 여기가 아니라 harness repo에 PR.

@../bananatouch-harness/rules/ai-agent-principles.md
@../bananatouch-harness/rules/commit-conventions.md
@../bananatouch-harness/rules/security.md

---

## Chaeshin CBR Memory (MCP)

이 프로젝트에는 Chaeshin MCP 서버가 등록되어 있다. 코드 작업을 하면서 패턴을
기억으로 쌓아 다음 작업에 재사용한다. 사용자에게 노출되는 통합 가이드는
[`chaeshin/integrations/claude_code/CLAUDE.md`](chaeshin/integrations/claude_code/CLAUDE.md) — 이게 정본이고, 아래는 그 요약 + 이 repo에서 작업할 때의 추가 지침이다.

### 기본 원칙

- **그래프가 모든 레이어에 있다.** L1=리프(도구 1회), L{n}=상위. 고정 3단계 아님.
- **outcome.status 는 3-state.** retain은 항상 `pending`. 성공/실패는 사용자 verdict로만 전환.
- **그래프 자체를 바꾸면 `chaeshin_revise`** — 다운스트림 자식이 자동으로 `pending` 회귀.

### 작업 시작 전 — `chaeshin_retrieve`

3+ tool call 또는 multi-step 작업이면 먼저 호출:

- `query` = 사용자 요청, `keywords` = 핵심 단어 콤마 구분
- 응답: `successes`(>0.7 유사도면 따라가기), `warnings`(피해야 할 패턴), `pending`(아직 판정 안 난 비슷한 케이스)
- 복잡한 트리는 `include_children=true` 로 한 번에 가져오기

### 작업 끝나면 — `chaeshin_retain` (pending)

```
chaeshin_retain(
  request="<사용자 요청>",
  category="<bug-fix|feature|deploy|...>",
  keywords="...",
  graph={"nodes":[...], "edges":[...]},
  layer="L1"  # 도구 호출 하나하나면 L1
)
```

`success` 파라미터는 없다. status 는 항상 `pending` 으로 들어간다.

### 사용자 verdict 신호 읽기 — `chaeshin_verdict`

**Success signals** (status="success"):
- "됐다", "고마워", "완벽해", "좋아", "ㅇㅇ"
- "커밋해줘", "푸쉬 해줘", "다음 거 해줘"
- 기술적: tests pass, build succeeds, CI green

**Failure signals** (status="failure"):
- "아니 그게 아니라", "이거 아닌데", "다시 해줘"
- "이거 왜 안돼?", "왜 이래"
- "되돌려줘", "롤백해줘"
- 기술적: test fail, build error, CI red

**모호하면 그냥 pending 유지.** 추측해서 verdict 호출하지 마라.

`note`에는 사용자 원문을 가능하면 인용.

### 그래프 자체가 바뀔 때 — `chaeshin_revise`

피드백이 그래프 구조에 대한 거면 (`이 단계 빼`, `순서 바꿔`, `이걸 두 개로 쪼개`)
단순 feedback이 아니라 revise:

```
chaeshin_revise(
  case_id=<...>,
  graph={"nodes":[...], "edges":[...]},
  reason="<왜>",
  cascade=true
)
```

응답의 `orphaned_children` 은 사용자에게 보고 — 어떻게 처리할지 사용자 결정.

### 분해가 필요한 복잡 작업

L4 → L3 → L2 → L1 순서로 retain, 매 단계 `parent_case_id` + `parent_node_id` 로 체인 연결.
도구 한 번 호출로 끝나는 leaf까지 내려갈 때까지 재귀.

### Tool graph 형식

```json
{
  "nodes": [
    {"id": "n1", "tool": "Read", "note": "Understand the issue"},
    {"id": "n2", "tool": "Edit", "note": "Apply fix"},
    {"id": "n3", "tool": "Bash", "note": "Run tests"}
  ],
  "edges": [
    {"from": "n2", "to": "n3", "condition": "n2.output.applied == true"}
  ]
}
```

`params_hint`(node), `condition`(edge) 옵션. 분기/루프 흐름에 유용.

---

## Project Conventions

- Language: Python 3.10+ with `from __future__ import annotations`
- Dependencies: structlog for logging, dataclasses for schemas
- Tests: pytest + pytest-asyncio, run with `uv run pytest tests/ -v`
- CI: GitHub Actions matrix (3.10, 3.11, 3.12), use `uv sync --extra dev` (NOT `--all-extras`)
- Integrations: optional extras (openai, chroma, llm, demo)
- Entry point: `chaeshin` CLI via `[project.scripts]`
- Korean comments in core code, English in README/docs
- Monitor UI: Next.js (chaeshin-monitor/), shadcn/ui + React Flow

## Environment Variables

| Var | Default | Used by |
|-----|---------|---------|
| `OPENAI_API_KEY` | — | OpenAIAdapter (LLM + 임베딩), ReAct demos |
| `CHAESHIN_STORE_DIR` | `~/.chaeshin/` | MCP server / migrations — DB 위치 오버라이드 |
| `CHAESHIN_DB_PATH` | `~/.chaeshin/chaeshin.db` | monitor 의 better-sqlite3 reader |
| `CHAESHIN_DEMO_PERSIST` | `0` | examples — `1`이면 ReAct 데모가 실제 DB에 저장 |
| `CHAESHIN_LLM_MODEL` | `gpt-4o-mini` | OpenAIAdapter 모델 오버라이드 |
| `CHAESHIN_EMBEDDING_MODEL` | `text-embedding-3-small` | 임베딩 모델 오버라이드 |
