"""
SQLite 백엔드 — 케이스 / 임베딩 / 이벤트 / 계층 엣지 영속화.

표준 라이브러리 sqlite3만 사용 (의존성 추가 없음).
스키마:
  - cases          : CBR 케이스 본체 (JSON 필드 + 검색용 인덱스 컬럼)
  - case_embeddings: case_id → 임베딩 벡터 (JSON 배열)
  - events         : 모든 MCP 호출 타임라인
  - hierarchy_edges: parent/child 관계 (CaseMetadata와 중복이지만 조인 편의용)
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from chaeshin.schema import (
    Case,
    CaseMetadata,
    GraphEdge,
    GraphNode,
    Outcome,
    ProblemFeatures,
    Solution,
    ToolGraph,
)

logger = structlog.get_logger(__name__)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cases (
    case_id        TEXT PRIMARY KEY,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    layer          TEXT NOT NULL DEFAULT 'L1',
    parent_case_id TEXT NOT NULL DEFAULT '',
    category       TEXT NOT NULL DEFAULT '',
    success        INTEGER NOT NULL DEFAULT 1,
    feedback_count INTEGER NOT NULL DEFAULT 0,
    difficulty     INTEGER NOT NULL DEFAULT 0,
    version        INTEGER NOT NULL DEFAULT 2,
    problem_json   TEXT NOT NULL,
    solution_json  TEXT NOT NULL,
    outcome_json   TEXT NOT NULL,
    metadata_json  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_layer    ON cases(layer);
CREATE INDEX IF NOT EXISTS idx_cases_parent   ON cases(parent_case_id);
CREATE INDEX IF NOT EXISTS idx_cases_category ON cases(category);
CREATE INDEX IF NOT EXISTS idx_cases_success  ON cases(success);

CREATE TABLE IF NOT EXISTS case_embeddings (
    case_id       TEXT PRIMARY KEY,
    embedding_json TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    session_id    TEXT NOT NULL DEFAULT '',
    case_ids_json TEXT NOT NULL DEFAULT '[]',
    payload_json  TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_ts    ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_type  ON events(event_type);

CREATE TABLE IF NOT EXISTS hierarchy_edges (
    parent_case_id TEXT NOT NULL,
    child_case_id  TEXT NOT NULL,
    parent_node_id TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    PRIMARY KEY(parent_case_id, child_case_id)
);

CREATE INDEX IF NOT EXISTS idx_hierarchy_child ON hierarchy_edges(child_case_id);
"""


class SQLiteBackend:
    """Chaeshin 영속화 백엔드.

    같은 DB 인스턴스를 CaseStore 영속화와 event_log 양쪽에서 공유.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._lock, self._connect() as conn:
            conn.executescript(SCHEMA_SQL)

    # ── Cases ────────────────────────────────────────────────────────

    def upsert_case(self, case: Case, embedding: Optional[List[float]] = None):
        meta = case.metadata
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cases (
                    case_id, created_at, updated_at, layer, parent_case_id,
                    category, success, feedback_count, difficulty, version,
                    problem_json, solution_json, outcome_json, metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(case_id) DO UPDATE SET
                    updated_at     = excluded.updated_at,
                    layer          = excluded.layer,
                    parent_case_id = excluded.parent_case_id,
                    category       = excluded.category,
                    success        = excluded.success,
                    feedback_count = excluded.feedback_count,
                    difficulty     = excluded.difficulty,
                    version        = excluded.version,
                    problem_json   = excluded.problem_json,
                    solution_json  = excluded.solution_json,
                    outcome_json   = excluded.outcome_json,
                    metadata_json  = excluded.metadata_json
                """,
                (
                    meta.case_id,
                    meta.created_at,
                    meta.updated_at,
                    getattr(meta, "layer", "L1") or "L1",
                    getattr(meta, "parent_case_id", "") or "",
                    case.problem_features.category or "",
                    1 if case.outcome.success else 0,
                    getattr(meta, "feedback_count", 0),
                    getattr(meta, "difficulty", 0),
                    getattr(meta, "version", 2),
                    json.dumps(asdict(case.problem_features), ensure_ascii=False),
                    json.dumps(asdict(case.solution), ensure_ascii=False),
                    json.dumps(asdict(case.outcome), ensure_ascii=False),
                    json.dumps(asdict(meta), ensure_ascii=False),
                ),
            )
            if embedding is not None:
                conn.execute(
                    """
                    INSERT INTO case_embeddings(case_id, embedding_json)
                    VALUES(?, ?)
                    ON CONFLICT(case_id) DO UPDATE SET embedding_json = excluded.embedding_json
                    """,
                    (meta.case_id, json.dumps(embedding)),
                )

    def delete_case(self, case_id: str):
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))

    def load_all_cases(self) -> List[Case]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT problem_json, solution_json, outcome_json, metadata_json "
                "FROM cases ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_case(r) for r in rows]

    def load_embeddings(self) -> Dict[str, List[float]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT case_id, embedding_json FROM case_embeddings"
            ).fetchall()
        return {r["case_id"]: json.loads(r["embedding_json"]) for r in rows}

    # ── Hierarchy ───────────────────────────────────────────────────

    def link(self, parent_id: str, child_id: str, parent_node_id: str = ""):
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO hierarchy_edges
                    (parent_case_id, child_case_id, parent_node_id, created_at)
                VALUES (?,?,?,?)
                """,
                (parent_id, child_id, parent_node_id, datetime.now().isoformat()),
            )

    def hierarchy_edges(self) -> List[Dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT parent_case_id, child_case_id, parent_node_id, created_at "
                "FROM hierarchy_edges"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Events ──────────────────────────────────────────────────────

    def append_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        session_id: str = "",
        case_ids: Optional[List[str]] = None,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO events(ts, event_type, session_id, case_ids_json, payload_json)
                VALUES(?,?,?,?,?)
                """,
                (
                    datetime.now().isoformat(),
                    event_type,
                    session_id or "",
                    json.dumps(case_ids or [], ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False, default=str),
                ),
            )
            return cur.lastrowid

    def recent_events(
        self,
        since: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT id, ts, event_type, session_id, case_ids_json, payload_json FROM events"
        clauses: List[str] = []
        params: List[Any] = []
        if since:
            clauses.append("ts > ?")
            params.append(since)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(int(limit))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "event_type": r["event_type"],
                "session_id": r["session_id"],
                "case_ids": json.loads(r["case_ids_json"]),
                "payload": json.loads(r["payload_json"]),
            }
            for r in rows
        ]

    def event_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()
        return int(row["n"])


# ── helpers ──────────────────────────────────────────────────────────


def _row_to_case(row: sqlite3.Row) -> Case:
    pf_raw = json.loads(row["problem_json"])
    sol_raw = json.loads(row["solution_json"])
    out_raw = json.loads(row["outcome_json"])
    meta_raw = json.loads(row["metadata_json"])

    pf = ProblemFeatures(**pf_raw)

    tg_raw = sol_raw.get("tool_graph", {})
    tg = ToolGraph(
        nodes=[GraphNode(**n) for n in tg_raw.get("nodes", [])],
        edges=[GraphEdge(**e) for e in tg_raw.get("edges", [])],
        parallel_groups=tg_raw.get("parallel_groups", []),
        entry_nodes=tg_raw.get("entry_nodes", []),
        max_loops=tg_raw.get("max_loops", 3),
    )
    sol = Solution(tool_graph=tg)
    out = Outcome(**out_raw)
    meta = CaseMetadata(**meta_raw)
    return Case(problem_features=pf, solution=sol, outcome=out, metadata=meta)
