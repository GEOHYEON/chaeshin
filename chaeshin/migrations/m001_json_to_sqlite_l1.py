"""
Migration 001: JSON cases.json → SQLite + flat layer → L1.

멱등성: 여러 번 실행해도 안전.
- 기존 SQLite에 이미 있는 case_id는 건너뜀 (overwrite=False 기본값)
- JSON 파일은 `.bak` 사본 생성 후 원본 유지

사용법:
    python -m chaeshin.migrations.m001_json_to_sqlite_l1
    python -m chaeshin.migrations.m001_json_to_sqlite_l1 --overwrite
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import List, Tuple

import structlog

from chaeshin.case_store import CaseStore
from chaeshin.storage.sqlite_backend import SQLiteBackend

logger = structlog.get_logger(__name__)


DEFAULT_GLOBAL_DIR = Path.home() / ".chaeshin"
DEFAULT_DB_PATH = DEFAULT_GLOBAL_DIR / "chaeshin.db"
DEFAULT_JSON_PATH = DEFAULT_GLOBAL_DIR / "cases.json"


def migrate(
    json_path: Path,
    db_path: Path,
    overwrite: bool = False,
) -> Tuple[int, int]:
    """JSON 파일을 SQLite DB로 이관.

    Returns:
        (imported_count, skipped_count)
    """
    if not json_path.exists():
        logger.info("no_json_to_migrate", path=str(json_path))
        return (0, 0)

    backup_path = json_path.with_suffix(json_path.suffix + ".bak")
    if not backup_path.exists():
        shutil.copy2(json_path, backup_path)
        logger.info("backup_created", src=str(json_path), dst=str(backup_path))

    backend = SQLiteBackend(db_path)

    # 스테이징용 in-memory store: 기존 JSON 파싱
    staging = CaseStore(embed_fn=None, backend=None)
    with open(json_path, "r", encoding="utf-8") as f:
        staging.load_json(f.read())

    existing_ids = {c.metadata.case_id for c in backend.load_all_cases()}

    imported = 0
    skipped = 0
    for case in staging.cases:
        cid = case.metadata.case_id
        if cid in existing_ids and not overwrite:
            skipped += 1
            continue
        # flat → L1 정규화 (CaseMetadata.__post_init__ 에서도 처리되지만 안전망)
        if not getattr(case.metadata, "layer", ""):
            case.metadata.layer = "L1"
        case.metadata.version = 2
        backend.upsert_case(case, embedding=None)
        imported += 1

    logger.info(
        "migration_complete",
        imported=imported,
        skipped=skipped,
        db=str(db_path),
    )
    return (imported, skipped)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chaeshin JSON→SQLite migration")
    parser.add_argument("--json", default=str(DEFAULT_JSON_PATH))
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    imported, skipped = migrate(
        Path(args.json),
        Path(args.db),
        overwrite=args.overwrite,
    )
    print(f"imported={imported} skipped={skipped} db={args.db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
