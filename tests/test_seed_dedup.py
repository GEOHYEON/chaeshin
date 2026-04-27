"""BulkGenerator dedup 테스트 — 임베딩이 같은 두 후보 중 하나만 retain."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Dict, List

import pytest

from chaeshin.seed import BulkGenerator, open_seed_store


SAMPLE_PAYLOAD = {
    "request": "Cleanup tmp files",
    "category": "ops",
    "keywords": ["cleanup", "tmp"],
    "constraints": [],
    "graph": {
        "nodes": [
            {"id": "n1", "tool": "Bash", "note": "rm -rf /tmp/foo", "params_hint": {}}
        ],
        "edges": [],
    },
}

INVALID_TOOL_PAYLOAD = {
    "request": "Use forbidden tool",
    "category": "ops",
    "keywords": ["x"],
    "constraints": [],
    "graph": {
        "nodes": [{"id": "n1", "tool": "ForbiddenTool", "note": "..."}],
        "edges": [],
    },
}


def _stub_llm_factory(payloads: List[Dict]):
    """payloads 를 순차로 돌려주는 stub. 모자라면 마지막 payload 반복."""
    idx = {"i": 0}

    async def llm_fn(messages):
        i = idx["i"]
        payload = payloads[i] if i < len(payloads) else payloads[-1]
        idx["i"] += 1
        return json.dumps(payload, ensure_ascii=False)

    return llm_fn


def _identical_embedder(text: str) -> List[float]:
    """모든 텍스트에 같은 벡터 — 코사인 유사도 1.0 으로 dedup 강제 발동."""
    return [1.0, 0.0, 0.0]


def _diverse_embedder_factory():
    """매 호출마다 다른 직교 벡터 — dedup 발동 안 함."""
    counter = {"i": 0}

    def embed(text: str) -> List[float]:
        i = counter["i"]
        counter["i"] += 1
        # 16-dim one-hot 비슷한 벡터
        v = [0.0] * 16
        v[i % 16] = 1.0
        return v

    return embed


class TestDedupRejectsIdenticalEmbeddings:
    def test_three_identical_yields_one(self, tmp_path: Path):
        store = open_seed_store(
            embed_fn=_identical_embedder, db_path=str(tmp_path / "seed.db")
        )
        gen = BulkGenerator(
            llm_fn=_stub_llm_factory([SAMPLE_PAYLOAD]),
            store=store,
            embed_fn=_identical_embedder,
            similarity_threshold=0.85,
        )
        accepted = asyncio.run(
            gen.generate(
                topic="ops cleanup",
                tool_allowlist=["Bash"],
                count=3,
                max_attempts_per_case=2,
            )
        )
        assert len(accepted) == 1
        assert len(store.cases) == 1

    def test_diverse_yields_multiple(self, tmp_path: Path):
        embed = _diverse_embedder_factory()
        store = open_seed_store(embed_fn=embed, db_path=str(tmp_path / "seed.db"))
        # 매번 같은 payload 라도 임베딩이 다르므로 dedup 안 걸림
        gen = BulkGenerator(
            llm_fn=_stub_llm_factory([SAMPLE_PAYLOAD]),
            store=store,
            embed_fn=embed,
            similarity_threshold=0.85,
        )
        accepted = asyncio.run(
            gen.generate(
                topic="ops",
                tool_allowlist=["Bash"],
                count=3,
                max_attempts_per_case=1,
            )
        )
        assert len(accepted) == 3


class TestToolAllowlistEnforcement:
    def test_invalid_tool_is_rejected(self, tmp_path: Path):
        store = open_seed_store(db_path=str(tmp_path / "seed.db"))
        gen = BulkGenerator(
            llm_fn=_stub_llm_factory([INVALID_TOOL_PAYLOAD]),
            store=store,
            embed_fn=None,
            similarity_threshold=0.85,
        )
        accepted = asyncio.run(
            gen.generate(
                topic="ops",
                tool_allowlist=["Bash"],  # ForbiddenTool 은 허용 안 됨
                count=1,
                max_attempts_per_case=2,
            )
        )
        assert len(accepted) == 0
        assert len(store.cases) == 0


class TestKeywordJaccardFallback:
    def test_jaccard_dedup_when_no_embed_fn(self, tmp_path: Path):
        # 같은 category + 같은 keywords → Jaccard 1.0 → 두번째부터 reject
        store = open_seed_store(db_path=str(tmp_path / "seed.db"))
        gen = BulkGenerator(
            llm_fn=_stub_llm_factory([SAMPLE_PAYLOAD]),
            store=store,
            embed_fn=None,  # fallback 경로
            similarity_threshold=0.85,
            jaccard_threshold=0.7,
        )
        accepted = asyncio.run(
            gen.generate(
                topic="ops",
                tool_allowlist=["Bash"],
                count=3,
                max_attempts_per_case=2,
            )
        )
        assert len(accepted) == 1
