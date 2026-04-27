"""Promote — staging seed.db 의 케이스를 main chaeshin.db 로 옮긴다.

기본은 새 case_id 발급 + ``metadata.source = "promoted_from:<old_id>"`` 백링크.
같은 마커가 main 에 있으면 skip (idempotent). ``force=True`` 면 새 id 로 한 번 더 발급.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import List, Tuple

import structlog

from chaeshin.case_store import CaseStore
from chaeshin.schema import Case, CaseMetadata, Outcome, ProblemFeatures, Solution

logger = structlog.get_logger(__name__)


PROMOTED_PREFIX = "promoted_from:"


def promote_cases(
    seed_store: CaseStore,
    main_store: CaseStore,
    case_ids: List[str],
    *,
    regenerate_ids: bool = True,
    force: bool = False,
) -> List[Tuple[str, str]]:
    """Seed → main 으로 케이스 복사.

    Args:
        seed_store: staging CaseStore (보통 ``open_seed_store()`` 결과).
        main_store: main CaseStore (보통 monitor / MCP 가 쓰는 chaeshin.db).
        case_ids: promote 할 seed case_id 리스트.
        regenerate_ids: True (기본) — 새 uuid 발급. False 면 같은 id 유지 (위험).
        force: True 면 main 에 ``promoted_from:<id>`` 마커가 이미 있어도 한 번 더 발급.

    Returns:
        ``[(old_seed_id, new_main_id), ...]`` — skip 된 항목은 ``new_main_id == ""``.
    """
    if not case_ids:
        return []

    existing_markers = _existing_markers(main_store)
    results: List[Tuple[str, str]] = []

    for old_id in case_ids:
        seed_case = seed_store.get_case_by_id(old_id)
        if seed_case is None:
            logger.warning("seed_case_not_found", case_id=old_id)
            results.append((old_id, ""))
            continue

        marker = f"{PROMOTED_PREFIX}{old_id}"
        if not force and marker in existing_markers:
            logger.info("seed_already_promoted", old_id=old_id)
            results.append((old_id, ""))
            continue

        new_case = _clone_for_promotion(seed_case, marker, regenerate_ids=regenerate_ids)
        new_id = main_store.retain(new_case)
        existing_markers.add(marker)  # in-batch dedup
        results.append((old_id, new_id))
        logger.info("seed_promoted", old_id=old_id, new_id=new_id)

    return results


def _existing_markers(main_store: CaseStore) -> set:
    """Main store 에서 ``source`` 가 ``promoted_from:...`` 인 마커 set 을 만든다."""
    markers = set()
    for c in main_store.cases:
        src = getattr(c.metadata, "source", "") or ""
        if src.startswith(PROMOTED_PREFIX):
            markers.add(src)
    return markers


def _clone_for_promotion(
    seed_case: Case,
    marker: str,
    regenerate_ids: bool,
) -> Case:
    """Seed case 를 deep copy 후 마커/새 id 부착. 자식 링크는 끊는다 (v1: flat).

    v1 은 flat 시드 전제 — 자식 토폴로지는 promote 하지 않는다.
    """
    raw = asdict(seed_case)
    pf = ProblemFeatures(
        request=raw["problem_features"]["request"],
        category=raw["problem_features"]["category"],
        keywords=list(raw["problem_features"].get("keywords", [])),
        constraints=list(raw["problem_features"].get("constraints", [])),
        context=copy.deepcopy(raw["problem_features"].get("context", {})),
    )
    sol = copy.deepcopy(seed_case.solution)
    out = Outcome(
        status="pending",  # promote 시점에도 pending — 사용자 verdict 권한 보호
        result_summary=raw["outcome"].get("result_summary", ""),
        tools_executed=raw["outcome"].get("tools_executed", 0),
    )

    new_id = str(uuid.uuid4()) if regenerate_ids else seed_case.metadata.case_id
    now = datetime.now().isoformat()
    meta = CaseMetadata(
        case_id=new_id,
        created_at=now,
        updated_at=now,
        source=marker,
        tags=list(seed_case.metadata.tags) + ["promoted"],
        difficulty=seed_case.metadata.difficulty,
        wait_mode=seed_case.metadata.wait_mode,
        deadline_at="",
    )
    return Case(problem_features=pf, solution=sol, outcome=out, metadata=meta)
