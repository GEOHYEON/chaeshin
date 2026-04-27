"""Scenario seed 생성용 LLM 프롬프트.

LLM 한 번 호출 = 시나리오 1개 + 그래프 1개. 배치 생성은 ``BulkGenerator`` 가 N번 호출.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


SCENARIO_SYSTEM_PROMPT = """당신은 chaeshin CBR 메모리에 들어갈 시드 케이스를 한 건 만든다.
시드 케이스 = (사용자가 던질 법한 시나리오 요청, 그 요청을 풀기 위한 Tool Graph).

토픽: {topic}

가용 도구 (이 목록 안에서만 tool 필드를 채워라):
{tools_section}

규칙:
1. ``request`` — 사용자가 자연어로 던질 법한 한 줄 요청.
2. ``category`` — 토픽을 좁게 표현한 슬러그 (예: "bug-fix", "deploy", "med-intake").
3. ``keywords`` — 검색용 핵심 단어 3~5개.
4. ``constraints`` — 도메인 제약 (없으면 빈 배열).
5. ``graph.nodes`` — 각 노드는 {{"id", "tool", "note", "params_hint"}} 키를 가진다.
   - ``tool`` 은 위 가용 도구 목록의 이름과 정확히 일치해야 한다.
   - 노드 1~6개. 너무 거대한 그래프 금지 — 시드는 단일 케이스 (자식 없음).
6. ``graph.edges`` — 각 엣지는 {{"from_node", "to_node", "condition"}} (condition optional).

{negative_section}{sample_section}
JSON 만 출력. 다른 텍스트 금지.

출력 스키마:
{{
  "request": "...",
  "category": "...",
  "keywords": ["..."],
  "constraints": ["..."],
  "graph": {{
    "nodes": [{{"id": "n1", "tool": "<allowed-tool>", "note": "...", "params_hint": {{}}}}],
    "edges": [{{"from_node": "n1", "to_node": "n2", "condition": null}}]
  }}
}}
"""


def build_scenario_prompt(
    topic: str,
    tool_allowlist: List[str],
    sample_seeds: Optional[List[Dict[str, Any]]] = None,
    avoid_themes: Optional[List[str]] = None,
) -> str:
    """LLM system prompt 를 조립한다.

    Args:
        topic: 자연어 토픽 (예: "T2DM 진료").
        tool_allowlist: 허용 도구 이름 목록 — LLM 출력 graph 의 tool 필드는 여기에 한정.
        sample_seeds: 1-shot 예시 (각 dict 는 최소 ``request`` 와 ``graph`` 보유).
        avoid_themes: 재시도 시 직전 reject 된 시나리오의 request 텍스트 — LLM 이 분기 유도.

    Returns:
        포맷된 system prompt 문자열.
    """
    tools_section = "\n".join(f"  - {t}" for t in tool_allowlist) or "  (없음)"

    sample_section = ""
    if sample_seeds:
        compact = [
            {
                "request": s.get("request", ""),
                "graph": s.get("graph", {}),
            }
            for s in sample_seeds
        ]
        sample_section = (
            "참고할 1-shot 예시 (스타일만 따라가고 내용은 새로 만든다):\n"
            f"{json.dumps(compact, ensure_ascii=False, indent=2)}\n\n"
        )

    negative_section = ""
    if avoid_themes:
        joined = "\n".join(f"  - {t}" for t in avoid_themes)
        negative_section = (
            "다음 주제와 너무 비슷한 시나리오는 피하라 (이미 생성됨):\n"
            f"{joined}\n\n"
        )

    return SCENARIO_SYSTEM_PROMPT.format(
        topic=topic,
        tools_section=tools_section,
        sample_section=sample_section,
        negative_section=negative_section,
    )
