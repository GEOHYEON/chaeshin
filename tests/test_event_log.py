"""EventLog 테스트."""

from __future__ import annotations

from pathlib import Path

from chaeshin.event_log import EventLog
from chaeshin.storage.sqlite_backend import SQLiteBackend


class TestEventLog:
    def test_record_with_backend(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "c.db")
        log = EventLog(backend, session_id="session-1")

        rid = log.record("retrieve", {"query": "deploy"}, case_ids=["a", "b"])
        assert rid is not None

        events = backend.recent_events()
        assert len(events) == 1
        assert events[0]["session_id"] == "session-1"
        assert events[0]["case_ids"] == ["a", "b"]
        assert events[0]["payload"]["query"] == "deploy"

    def test_record_without_backend_is_noop(self):
        log = EventLog(backend=None)
        assert log.record("retrieve", {}) is None

    def test_auto_session_id(self, tmp_path: Path):
        backend = SQLiteBackend(tmp_path / "c.db")
        log = EventLog(backend)
        assert log.session_id
