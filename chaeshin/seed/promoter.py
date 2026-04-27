"""Promote — staging seed.db 의 케이스를 main chaeshin.db 로 옮긴다.

기본은 새 case_id 발급 + ``metadata.source = "promoted_from:<old_id>"`` 백링크.
같은 마커가 main 에 있으면 skip (idempotent). ``force=True`` 면 새 id 로 한 번 더 발급.

v2: 토폴로지 인식 promote — 입력 ``case_ids`` 안에 부모-자식 관계가 있으면
부모 먼저 promote, 자식의 ``parent_case_id`` 를 새 main id 로 재매핑하고
``main_store.link_parent_child`` 로 트리를 보존한다. 입력 리스트에 부모가 없는
seed 의 자식만 들어오면 main 에서 root 로 등록 (``parent_case_id=""``).
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Dict, List, Set, Tuple

import structlog

from chaeshin.case_store import CaseStore
from chaeshin.schema import Case, CaseMetadata, Outcome, ProblemFeatures

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
    """Seed → main 으로 케이스(트리 가능) 복사.

    Args:
        seed_store: staging CaseStore (보통 ``open_seed_store()`` 결과).
        main_store: main CaseStore (보통 monitor / MCP 가 쓰는 chaeshin.db).
        case_ids: promote 할 seed case_id 리스트. 입력에 부모-자식이 같이 있으면
            트리째 보존; 부모 없는 자식만 있으면 main 에서 root 로.
        regenerate_ids: True (기본) — 새 uuid 발급. False 면 같은 id 유지 (위험).
        force: True 면 main 에 ``promoted_from:<id>`` 마커가 이미 있어도 한 번 더 발급.

    Returns:
        ``[(old_seed_id, new_main_id), ...]`` — skip 된 항목은 ``new_main_id == ""``.
        반환 순서는 입력 순서가 아니라 토폴로지 순서 (부모 먼저).
    """
    if not case_ids:
        return []

    # 위상정렬: 입력 안에 부모가 있으면 그 부모를 먼저.
    ordered_ids = _topological_sort(seed_store, case_ids)

    existing_markers = _existing_markers(main_store)
    id_map: Dict[str, str] = {}  # old seed id → new main id (이번 배치)
    results: List[Tuple[str, str]] = []
    input_set: Set[str] = set(case_ids)

    for old_id in ordered_ids:
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

        # 부모 재매핑: 입력 리스트에 같이 있는 부모면 새 id 로, 아니면 끊음.
        seed_parent = getattr(seed_case.metadata, "parent_case_id", "") or ""
        new_parent = id_map.get(seed_parent, "") if seed_parent in input_set else ""
        new_parent_node = (
            getattr(seed_case.metadata, "parent_node_id", "") or ""
        ) if new_parent else ""

        new_case = _clone_for_promotion(
            seed_case,
            marker,
            regenerate_ids=regenerate_ids,
            parent_case_id=new_parent,
            parent_node_id=new_parent_node,
        )
        new_id = main_store.retain(new_case)
        existing_markers.add(marker)
        id_map[old_id] = new_id

        if new_parent:
            main_store.link_parent_child(new_parent, new_id, new_parent_node)

        results.append((old_id, new_id))
        logger.info(
            "seed_promoted",
            old_id=old_id,
            new_id=new_id,
            new_parent=new_parent or None,
        )

    return results


def _topological_sort(seed_store: CaseStore, case_ids: List[str]) -> List[str]:
    """부모 먼저 오도록 위상정렬. 입력 안에 부모가 없는 case 는 root 로 취급.

    Kahn 알고리즘 — 사이클 감지되면 남은 노드는 입력 순서로 부착 (best-effort).
    """
    ids = [cid for cid in case_ids]  # preserve original order for tie-break
    seen = set(ids)
    in_input_parent: Dict[str, str] = {}
    children_of: Dict[str, List[str]] = {}
    for cid in ids:
        case = seed_store.get_case_by_id(cid)
        if case is None:
            continue
        pid = getattr(case.metadata, "parent_case_id", "") or ""
        if pid in seen:
            in_input_parent[cid] = pid
            children_of.setdefault(pid, []).append(cid)

    indeg = {cid: (1 if cid in in_input_parent else 0) for cid in ids}
    ready = [cid for cid in ids if indeg[cid] == 0]
    out: List[str] = []
    while ready:
        cur = ready.pop(0)
        out.append(cur)
        for child in children_of.get(cur, []):
            indeg[child] -= 1
            if indeg[child] == 0:
                ready.append(child)

    if len(out) < len(ids):
        # 사이클 또는 중복 — 남은 항목을 그냥 뒤에 붙임.
        leftover = [cid for cid in ids if cid not in out]
        logger.warning("seed_promote_topology_residual", leftover=leftover)
        out.extend(leftover)
    return out


def _existing_markers(main_store: CaseStore) -> Set[str]:
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
    parent_case_id: str = "",
    parent_node_id: str = "",
) -> Case:
    """Seed case 를 deep copy 후 마커/새 id/재매핑된 parent 부착."""
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
        status="pending",
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
        parent_case_id=parent_case_id,
        parent_node_id=parent_node_id,
    )
    return Case(problem_features=pf, solution=sol, outcome=out, metadata=meta)
