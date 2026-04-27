"""Seed store factory — main chaeshin.db 와 분리된 staging CaseStore.

기본 경로 ``~/.chaeshin/seed.db`` (override ``CHAESHIN_SEED_DB_PATH``).
스키마/백엔드는 main 과 동일 — ``SQLiteBackend`` 를 다른 파일 경로로 띄울 뿐.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

from chaeshin.case_store import CaseStore
from chaeshin.storage.sqlite_backend import SQLiteBackend


def default_seed_db_path() -> str:
    """Seed DB 기본 경로. 환경변수 ``CHAESHIN_SEED_DB_PATH`` 로 오버라이드."""
    env = os.getenv("CHAESHIN_SEED_DB_PATH", "")
    if env:
        return env
    base = os.path.expanduser(os.getenv("CHAESHIN_STORE_DIR", "~/.chaeshin"))
    return os.path.join(base, "seed.db")


def open_seed_store(
    embed_fn: Optional[Callable[[str], List[float]]] = None,
    db_path: Optional[str] = None,
) -> CaseStore:
    """Seed staging 용 CaseStore 를 연다.

    Args:
        embed_fn: 임베딩 함수 (있으면 retain 시 임베딩 저장 → dedup 가능).
        db_path: 명시적 DB 경로. None 이면 ``default_seed_db_path()``.

    Returns:
        ``CaseStore`` — 시드 케이스 저장 전용. main 과 완전 격리.
    """
    path = db_path or default_seed_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    backend = SQLiteBackend(path)
    return CaseStore(
        embed_fn=embed_fn,
        similarity_threshold=0.5,
        backend=backend,
        auto_load=True,
    )
