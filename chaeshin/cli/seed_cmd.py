"""``chaeshin seed`` CLI subcommands.

Subcommands:
    generate   LLM 으로 시드 케이스 N건 생성 → seed.db 에 retain
    list       seed.db 의 케이스 목록 출력
    export     seed.db → JSON 파일
    import     JSON 파일 → seed.db
    promote    seed.db → main chaeshin.db 로 새 id 부여 후 복사
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import List, Optional

from chaeshin.case_store import CaseStore
from chaeshin.seed import (
    BulkGenerator,
    default_seed_db_path,
    open_seed_store,
    promote_cases,
)
from chaeshin.storage.sqlite_backend import SQLiteBackend


# ── helpers ──────────────────────────────────────────────────────────


def _main_db_path() -> str:
    base = os.path.expanduser(os.getenv("CHAESHIN_STORE_DIR", "~/.chaeshin"))
    return os.path.join(base, "chaeshin.db")


def _open_main_store() -> CaseStore:
    backend = SQLiteBackend(_main_db_path())
    return CaseStore(backend=backend, auto_load=True)


def _get_openai_adapter():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from chaeshin.integrations.openai import OpenAIAdapter

        return OpenAIAdapter(api_key=api_key)
    except ImportError:
        return None


def _print(msg: str) -> None:
    print(msg, flush=True)


def _ndjson(obj: dict) -> None:
    """UI 가 읽을 수 있게 NDJSON 한 줄 emit."""
    print(json.dumps(obj, ensure_ascii=False), flush=True)


# ── commands ─────────────────────────────────────────────────────────


def cmd_generate(args: argparse.Namespace) -> int:
    adapter = _get_openai_adapter()
    if adapter is None:
        _print("ERROR: OPENAI_API_KEY 가 필요합니다 (chaeshin seed generate).")
        return 2
    seed_store = open_seed_store(embed_fn=adapter.embed_fn, db_path=args.db or None)
    tools = [t.strip() for t in (args.tools or "").split(",") if t.strip()]
    if not tools:
        _print("ERROR: --tools 가 비어있다 (콤마 구분).")
        return 2
    sample_seeds = None
    if args.sample_file:
        with open(args.sample_file, "r", encoding="utf-8") as f:
            sample_seeds = json.load(f)

    generator = BulkGenerator(
        llm_fn=adapter.llm_fn,
        store=seed_store,
        embed_fn=adapter.embed_fn,
        similarity_threshold=args.similarity_threshold,
    )
    accepted = asyncio.run(
        generator.generate(
            topic=args.topic,
            tool_allowlist=tools,
            count=args.count,
            sample_seeds=sample_seeds,
            max_attempts_per_case=args.max_attempts,
        )
    )
    _ndjson(
        {
            "event": "generate_done",
            "topic": args.topic,
            "requested": args.count,
            "accepted": len(accepted),
            "case_ids": [c.metadata.case_id for c in accepted],
            "db": seed_store.backend.db_path if seed_store.backend else "",
        }
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = open_seed_store(db_path=args.db or None)
    rows = []
    for c in store.cases:
        src = getattr(c.metadata, "source", "") or ""
        if args.topic and not src.endswith(args.topic) and args.topic not in src:
            continue
        rows.append(
            {
                "case_id": c.metadata.case_id,
                "request": c.problem_features.request,
                "source": src,
                "category": c.problem_features.category,
                "node_count": len(c.solution.tool_graph.nodes),
                "status": c.outcome.status,
            }
        )
    _print(json.dumps({"total": len(rows), "cases": rows}, ensure_ascii=False, indent=2))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = open_seed_store(db_path=args.db or None)
    payload = store.to_json()
    with open(args.path, "w", encoding="utf-8") as f:
        f.write(payload)
    _print(json.dumps({"event": "export_done", "path": args.path, "count": len(store.cases)}))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    store = open_seed_store(db_path=args.db or None)
    with open(args.path, "r", encoding="utf-8") as f:
        raw = f.read()
    before = len(store.cases)
    store.load_json(raw)
    # load_json 은 메모리만 채움 → 영속화 위해 retain 한 번 더
    for case in store.cases[before:]:
        store.retain(case)
    _print(
        json.dumps(
            {
                "event": "import_done",
                "path": args.path,
                "added": len(store.cases) - before,
            }
        )
    )
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    seed_store = open_seed_store(db_path=args.seed_db or None)
    main_store = _open_main_store()

    if args.all:
        ids = [c.metadata.case_id for c in seed_store.cases]
    elif args.ids:
        ids = [s.strip() for s in args.ids.split(",") if s.strip()]
    else:
        _print("ERROR: --ids ID1,ID2 또는 --all 중 하나가 필요합니다.")
        return 2

    results = promote_cases(
        seed_store=seed_store,
        main_store=main_store,
        case_ids=ids,
        regenerate_ids=True,
        force=args.force,
    )
    promoted = [(o, n) for o, n in results if n]
    skipped = [o for o, n in results if not n]
    _print(
        json.dumps(
            {
                "event": "promote_done",
                "promoted": [{"old": o, "new": n} for o, n in promoted],
                "skipped": skipped,
                "main_db": _main_db_path(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


# ── subparser registration ───────────────────────────────────────────


def add_subparser(subparsers) -> None:
    """``main.py`` 에서 호출 — ``chaeshin seed <subcmd>`` 트리 등록."""
    p_seed = subparsers.add_parser("seed", help="시드 케이스 생성/관리")
    seed_sub = p_seed.add_subparsers(dest="seed_command")

    p_gen = seed_sub.add_parser("generate", help="LLM 으로 시드 케이스 생성")
    p_gen.add_argument("--topic", required=True, help="자연어 토픽")
    p_gen.add_argument("--tools", required=True, help="콤마 구분 도구 이름 allowlist")
    p_gen.add_argument("--count", type=int, default=5, help="생성할 케이스 수")
    p_gen.add_argument("--db", default=None, help="seed.db 경로 (기본: 환경)")
    p_gen.add_argument("--sample-file", default=None, help="1-shot 시드 JSON 파일")
    p_gen.add_argument(
        "--similarity-threshold", type=float, default=0.85, help="dedup 임계값"
    )
    p_gen.add_argument("--max-attempts", type=int, default=3, help="케이스당 재시도 횟수")
    p_gen.set_defaults(func=cmd_generate)

    p_list = seed_sub.add_parser("list", help="seed.db 케이스 목록")
    p_list.add_argument("--topic", default=None, help="source 에 토픽 포함된 것만")
    p_list.add_argument("--db", default=None)
    p_list.set_defaults(func=cmd_list)

    p_exp = seed_sub.add_parser("export", help="seed.db → JSON 파일")
    p_exp.add_argument("path", help="출력 파일 경로")
    p_exp.add_argument("--db", default=None)
    p_exp.set_defaults(func=cmd_export)

    p_imp = seed_sub.add_parser("import", help="JSON 파일 → seed.db")
    p_imp.add_argument("path", help="입력 파일 경로")
    p_imp.add_argument("--db", default=None)
    p_imp.set_defaults(func=cmd_import)

    p_pro = seed_sub.add_parser("promote", help="seed.db → main chaeshin.db")
    p_pro.add_argument("--ids", default=None, help="콤마 구분 case_id 리스트")
    p_pro.add_argument("--all", action="store_true", help="seed.db 전부 promote")
    p_pro.add_argument("--force", action="store_true", help="이미 promote 된 케이스도 다시 발급")
    p_pro.add_argument("--seed-db", default=None, help="seed.db 경로 override")
    p_pro.set_defaults(func=cmd_promote)


def _print_help_if_no_subcommand(args: argparse.Namespace, parser: argparse.ArgumentParser) -> bool:
    if getattr(args, "seed_command", None) is None:
        parser.print_help()
        return True
    return False
