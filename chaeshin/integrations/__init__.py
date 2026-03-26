"""
Chaeshin Integrations — LLM 및 VectorDB 어댑터.

사용 가능한 통합:
- OpenAIAdapter: OpenAI LLM + 임베딩
- ChromaCaseStore: ChromaDB 기반 CBR 케이스 저장소
"""

__all__: list[str] = []

# Lazy imports — 의존성이 없어도 import 에러 안 남
try:
    from chaeshin.integrations.openai import OpenAIAdapter
    __all__.append("OpenAIAdapter")
except ImportError:
    pass

try:
    from chaeshin.integrations.chroma import ChromaCaseStore
    __all__.append("ChromaCaseStore")
except ImportError:
    pass
