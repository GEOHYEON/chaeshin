"""pass^k metric (τ-bench, Table 5 of the paper).

Definition (Yao et al. NeurIPS 2024):
    pass^k = mean over tasks of (probability that *all* k of k independent
              trials of the same task succeed)

Estimator from n trials (n ≥ k):
    For each task, with c successes out of n trials,
        p̂(all k succeed) = C(c,k) / C(n,k)
    Take the mean across tasks.

Reference: arXiv:2406.12045
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, List


def _binom(n: int, k: int) -> float:
    if k < 0 or k > n:
        return 0.0
    return math.comb(n, k)


def pass_at_k(records: Iterable[dict], k: int) -> float:
    """Records must include `task_id` and boolean `success`.

    Multiple trials per task_id are required (n ≥ k); we group by task_id.
    """
    by_task = defaultdict(list)
    for r in records:
        by_task[r.get("task_id", "?")].append(bool(r.get("success", False)))

    pass_k_per_task: List[float] = []
    for tid, results in by_task.items():
        n = len(results)
        c = sum(results)
        if n < k:
            # Not enough trials — skip rather than skew mean.
            continue
        denom = _binom(n, k)
        numer = _binom(c, k)
        pass_k_per_task.append(numer / denom if denom > 0 else 0.0)

    if not pass_k_per_task:
        return 0.0
    return sum(pass_k_per_task) / len(pass_k_per_task)
