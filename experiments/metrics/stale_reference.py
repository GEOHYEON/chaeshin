"""Chaeshin-specific metrics (Table 4 of the paper).

stale_reference_rate:
    Fraction of revise actions whose `removed_nodes` left at least one
    child case with a now-dangling parent_node_id. Should be 0% for
    cascade=True; the no-cascade ablation is expected to be ~10–15%.

cross_task_reuse_rate:
    Fraction of retrieve calls that return at least one match above
    similarity threshold. A proxy for "is the case bank actually
    helping after enough cases have accumulated?"
"""

from __future__ import annotations

from typing import Iterable, List


def stale_reference_rate(records: Iterable[dict]) -> float:
    """Aggregated from `extras.stale_refs` written by the chaeshin agent.

    Denominator: number of revise actions across all records.
    Numerator: total stale-ref count.
    """
    total_revises = 0
    total_stale = 0
    for r in records:
        ex = r.get("extras", {}) or {}
        # We don't directly count revises in extras; count from steps:
        for s in r.get("steps", []):
            if s.get("action") == "chaeshin_revise":
                total_revises += 1
        total_stale += int(ex.get("stale_refs", 0))
    if total_revises == 0:
        return 0.0
    return total_stale / total_revises


def cross_task_reuse_rate(records: Iterable[dict]) -> float:
    """Fraction of retrieves that returned at least one hit."""
    total_retrieves = 0
    total_hits = 0
    for r in records:
        ex = r.get("extras", {}) or {}
        total_retrieves += int(ex.get("n_retrieves", 0))
        total_hits += int(ex.get("retrieve_hits", 0))
    if total_retrieves == 0:
        return 0.0
    return total_hits / total_retrieves
