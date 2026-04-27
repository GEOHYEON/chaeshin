"""m003 — layer/depth 를 stored 에서 derived 로 전환.

이 마이그레이션:
  - cases 테이블의 ``layer`` 컬럼과 ``idx_cases_layer`` 인덱스 드롭
  - 각 metadata_json blob 에서 legacy ``layer`` / ``depth`` 키 제거 (있으면)
  - version 을 3 으로 bump

층수는 이제 ``CaseStore.derive_depth(case_id)`` 로 트리에서 계산. parent_case_id 만
저장되는 형태로 정착.

멱등: layer 컬럼이 이미 없으면 컬럼 드롭 단계 skip. metadata_json 에 키가 없으면
청소 단계 skip.

사용법:
    python -m chaeshin.migrations.m003_drop_layer
    python -m chaeshin.migrations.m003_drop_layer --db /path/to/chaeshin.db
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    rows = db.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def migrate(db_path: Path) -> dict:
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    try:
        # 1) metadata_json 청소 + version bump
        rows = db.execute(
            "SELECT case_id, metadata_json FROM cases"
        ).fetchall()
        cleaned = 0
        skipped = 0
        now = datetime.now().isoformat()
        for r in rows:
            meta = json.loads(r["metadata_json"])
            had_layer = "layer" in meta
            had_depth = "depth" in meta
            if not (had_layer or had_depth) and meta.get("version") == 3:
                skipped += 1
                continue
            meta.pop("layer", None)
            meta.pop("depth", None)
            meta["version"] = 3
            db.execute(
                "UPDATE cases SET metadata_json = ?, updated_at = ? WHERE case_id = ?",
                (json.dumps(meta, ensure_ascii=False), now, r["case_id"]),
            )
            cleaned += 1

        # 2) idx_cases_layer 드롭 (멱등)
        db.execute("DROP INDEX IF EXISTS idx_cases_layer")

        # 3) layer 컬럼 드롭 (SQLite 3.35+). 없으면 skip.
        cols = _columns(db, "cases")
        column_dropped = False
        if "layer" in cols:
            try:
                db.execute("ALTER TABLE cases DROP COLUMN layer")
                column_dropped = True
            except sqlite3.OperationalError as e:
                # 구 SQLite — 테이블 재생성 fallback
                _recreate_without_layer(db)
                column_dropped = True

        db.commit()
        return {
            "cleaned": cleaned,
            "skipped": skipped,
            "column_dropped": column_dropped,
            "db": str(db_path),
        }
    finally:
        db.close()


def _recreate_without_layer(db: sqlite3.Connection) -> None:
    """SQLite < 3.35 fallback — cases 테이블을 layer 컬럼 없이 재생성하고 데이터 복사."""
    db.execute("""
        CREATE TABLE cases_new (
            case_id        TEXT PRIMARY KEY,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            parent_case_id TEXT NOT NULL DEFAULT '',
            category       TEXT NOT NULL DEFAULT '',
            success        INTEGER NOT NULL DEFAULT 1,
            feedback_count INTEGER NOT NULL DEFAULT 0,
            difficulty     INTEGER NOT NULL DEFAULT 0,
            version        INTEGER NOT NULL DEFAULT 3,
            problem_json   TEXT NOT NULL,
            solution_json  TEXT NOT NULL,
            outcome_json   TEXT NOT NULL,
            metadata_json  TEXT NOT NULL
        )
    """)
    db.execute("""
        INSERT INTO cases_new (
            case_id, created_at, updated_at, parent_case_id, category,
            success, feedback_count, difficulty, version,
            problem_json, solution_json, outcome_json, metadata_json
        )
        SELECT case_id, created_at, updated_at, parent_case_id, category,
               success, feedback_count, difficulty, version,
               problem_json, solution_json, outcome_json, metadata_json
        FROM cases
    """)
    db.execute("DROP TABLE cases")
    db.execute("ALTER TABLE cases_new RENAME TO cases")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cases_parent   ON cases(parent_case_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cases_category ON cases(category)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_cases_success  ON cases(success)")


def main():
    ap = argparse.ArgumentParser(description="Drop stored layer column; layer becomes derived from tree.")
    ap.add_argument(
        "--db",
        default=os.path.expanduser("~/.chaeshin/chaeshin.db"),
        help="SQLite DB path (default: ~/.chaeshin/chaeshin.db)",
    )
    args = ap.parse_args()
    if not Path(args.db).exists():
        print(f"db not found: {args.db}")
        return
    result = migrate(Path(args.db))
    print(
        f"cleaned={result['cleaned']} skipped={result['skipped']} "
        f"column_dropped={result['column_dropped']} db={result['db']}"
    )


if __name__ == "__main__":
    main()
