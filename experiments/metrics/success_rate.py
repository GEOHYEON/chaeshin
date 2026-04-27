"""Success rate (Table 2 of the paper)."""

from __future__ import annotations

import math
from typing import Iterable, List, Tuple


def success_rate(records: Iterable[dict]) -> float:
    """Fraction of trials where success=True."""
    rs = list(records)
    if not rs:
        return 0.0
    return sum(1 for r in rs if r.get("success")) / len(rs)


def success_rate_with_se(records_by_seed: List[List[dict]]) -> Tuple[float, float]:
    """Mean and standard error across seeds.

    `records_by_seed[i]` is the list of trial dicts from seed i.
    Each list should cover the same task set (we average per-seed
    success rate, then take std across seeds).
    """
    if not records_by_seed:
        return 0.0, 0.0
    per_seed = [success_rate(seed_recs) for seed_recs in records_by_seed if seed_recs]
    if not per_seed:
        return 0.0, 0.0
    n = len(per_seed)
    mean = sum(per_seed) / n
    if n < 2:
        return mean, 0.0
    var = sum((x - mean) ** 2 for x in per_seed) / (n - 1)
    return mean, math.sqrt(var)
