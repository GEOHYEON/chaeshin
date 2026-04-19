"""
Event log — 모든 MCP 호출의 타임라인 기록.

SQLite 백엔드를 주입받는 얇은 래퍼.
backend=None이면 no-op (테스트/오프라인 환경 호환).

사용 예:
    log = EventLog(backend)
    log.record("retrieve", {"query": "...", "matched": [...]})
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

import structlog

from chaeshin.storage.sqlite_backend import SQLiteBackend

logger = structlog.get_logger(__name__)


class EventLog:
    """MCP 호출 이벤트 로거."""

    def __init__(self, backend: Optional[SQLiteBackend] = None, session_id: str = ""):
        self.backend = backend
        self.session_id = session_id or str(uuid.uuid4())

    def record(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        case_ids: Optional[List[str]] = None,
    ) -> Optional[int]:
        """이벤트 기록. backend 없으면 no-op."""
        if self.backend is None:
            return None
        try:
            return self.backend.append_event(
                event_type=event_type,
                payload=payload or {},
                session_id=self.session_id,
                case_ids=case_ids,
            )
        except Exception as exc:
            logger.warning("event_log_failed", event_type=event_type, error=str(exc))
            return None
