"""
OpenAI Adapter — LLM 호출 + 임베딩 생성.

GraphPlanner의 llm_fn과 CaseStore의 embed_fn을 제공합니다.

사용법:
    adapter = OpenAIAdapter(model="gpt-4o-mini")
    planner = GraphPlanner(llm_fn=adapter.llm_fn, tools=TOOLS)
    store = CaseStore(embed_fn=adapter.embed_fn)
"""

from __future__ import annotations

import structlog
from typing import Any, Dict, List, Optional

try:
    from openai import AsyncOpenAI, OpenAI
except ImportError as e:
    raise ImportError(
        "openai 패키지가 필요합니다: pip install 'chaeshin[llm]'"
    ) from e

logger = structlog.get_logger(__name__)


class OpenAIAdapter:
    """OpenAI API 어댑터.

    LLM 호출(비동기)과 임베딩 생성(동기)을 제공합니다.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        """
        Args:
            model: LLM 모델명 (gpt-4o, gpt-4o-mini 등)
            embedding_model: 임베딩 모델명
            api_key: OpenAI API 키 (None이면 환경변수 사용)
            temperature: LLM 온도
            max_tokens: 최대 토큰 수
        """
        self.model = model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._async_client = AsyncOpenAI(api_key=api_key)
        self._sync_client = OpenAI(api_key=api_key)

        logger.info(
            "openai_adapter_initialized",
            model=model,
            embedding_model=embedding_model,
        )

    async def llm_fn(self, messages: List[Dict[str, str]]) -> str:
        """GraphPlanner용 LLM 호출 함수.

        Args:
            messages: OpenAI 메시지 형식 [{"role": "system", "content": "..."}, ...]

        Returns:
            LLM 응답 텍스트
        """
        logger.info(
            "llm_call",
            model=self.model,
            messages_count=len(messages),
        )

        response = await self._async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        text = response.choices[0].message.content or ""

        logger.info(
            "llm_response",
            model=self.model,
            tokens_used=response.usage.total_tokens if response.usage else 0,
            response_length=len(text),
        )

        return text

    def embed_fn(self, text: str) -> List[float]:
        """CaseStore용 임베딩 생성 함수.

        Args:
            text: 임베딩할 텍스트

        Returns:
            임베딩 벡터
        """
        response = self._sync_client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )

        return response.data[0].embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """여러 텍스트를 한 번에 임베딩.

        Args:
            texts: 임베딩할 텍스트 목록

        Returns:
            임베딩 벡터 목록
        """
        if not texts:
            return []

        response = self._sync_client.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )

        return [d.embedding for d in response.data]
