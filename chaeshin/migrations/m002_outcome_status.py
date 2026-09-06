"""m002 — 기존 cases.outcome에 status/verdict 필드 추가.

확장된 스키마: outcome에 status ("success"|"failure"|"pending") + verdict_note/verdict_at,
metadata에 depth/wait_mode/deadline_at.

이 마이그레이션은 기존 20건을 대상으로:
  - outcome.success==True  → outcome.status="success"
  - outcome.success==False → outcome.status="failure"
  - metadata.depth=0, wait_mode="deadline", deadline_at=""
  - verdict_at = metadata.updated_at (이미 결정된 건이므로)

멱등: 이미 status가 있으면 건드리지 않음.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


def migrate(db_path: Path) -> dict:
    """기존 케이스에 3상태 outcome 및 verdict 메타데이터를 채운다.

    이미 ``outcome.status``가 있는 행은 건드리지 않아 반복 실행해도 안전하다.

    Returns:
        갱신·건너뜀 건수와 DB 경로를 담은 딕셔너리.
    """
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    try:
        rows = db.execute(
            "SELECT case_id, outcome_json, metadata_json FROM cases"
        ).fetchall()
        updated = 0
        skipped = 0
        now = datetime.now().isoformat()
        for r in rows:
            outcome = json.loads(r["outcome_json"])
            metadata = json.loads(r["metadata_json"])

            if "status" in outcome and outcome["status"]:
                skipped += 1
                continue

            success = bool(outcome.get("success", False))
            outcome["status"] = "success" if success else "failure"
            outcome.setdefault("verdict_note", "")
            outcome.setdefault("verdict_at", metadata.get("updated_at", now))

            metadata.setdefault("depth", 0)
            metadata.setdefault("wait_mode", "deadline")
            metadata.setdefault("deadline_at", "")

            db.execute(
                """
                UPDATE cases
                   SET outcome_json = ?, metadata_json = ?, updated_at = ?
                 WHERE case_id = ?
                """,
                (
                    json.dumps(outcome, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                    now,
                    r["case_id"],
                ),
            )
            updated += 1

        db.commit()
        return {"updated": updated, "skipped": skipped, "db": str(db_path)}
    finally:
        db.close()


def main():
    """기본 또는 지정 DB에 m002 마이그레이션을 실행한다."""
    ap = argparse.ArgumentParser(description="Backfill outcome.status on existing cases.")
    ap.add_argument(
        "--db",
        default=os.path.expanduser("~/.chaeshin/chaeshin.db"),
        help="SQLite DB path (default: ~/.chaeshin/chaeshin.db)",
    )
    args = ap.parse_args()
    result = migrate(Path(args.db))
    print(f"updated={result['updated']} skipped={result['skipped']} db={result['db']}")


if __name__ == "__main__":
    main()
