"""Read JSONL run logs → produce paper Tables 2-5 as JSON.

Usage:
    uv run python -m experiments.aggregate \\
        --logs experiments/logs/ \\
        --output experiments/results/tables.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from experiments.metrics import (
    cross_task_reuse_rate,
    pass_at_k,
    stale_reference_rate,
    success_rate,
    success_rate_with_se,
)


def _load_jsonl(p: Path) -> List[dict]:
    out = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.stderr.write(f"[WARN] bad JSON in {p}: {e}\n")
    return out


def _scan_logs(log_dir: Path) -> Dict[tuple, List[List[dict]]]:
    """Returns {(benchmark, agent): [seed_records, ...]} grouping."""
    by_cell: Dict[tuple, Dict[int, List[dict]]] = defaultdict(lambda: defaultdict(list))
    for path in sorted(log_dir.glob("*.jsonl")):
        records = _load_jsonl(path)
        for r in records:
            key = (r.get("benchmark_name", "?"), r.get("agent_name", "?"))
            seed = int(r.get("seed", 0))
            by_cell[key][seed].append(r)
    # Convert inner dict → ordered list-of-lists
    return {
        key: [seeds[s] for s in sorted(seeds.keys())]
        for key, seeds in by_cell.items()
    }


def build_table_main(by_cell: Dict[tuple, List[List[dict]]]) -> Dict[str, Any]:
    """Table 2: success rate per (benchmark, agent) with mean ± SE."""
    out: Dict[str, Any] = {}
    for (bench, agent), seed_lists in by_cell.items():
        mean, se = success_rate_with_se(seed_lists)
        out.setdefault(bench, {})[agent] = {
            "mean": mean,
            "se": se,
            "n_seeds": len(seed_lists),
        }
    return out


def build_table_ablation(by_cell: Dict[tuple, List[List[dict]]],
                         baseline_agent: str = "chaeshin_full") -> Dict[str, Any]:
    """Table 3: chaeshin variants relative to chaeshin_full."""
    chaeshin_variants = [
        "chaeshin_full",
        "chaeshin_no_cascade",
        "chaeshin_no_pending",
        "chaeshin_no_recursion",
    ]
    out: Dict[str, Any] = {}
    for (bench, agent), seed_lists in by_cell.items():
        if agent not in chaeshin_variants:
            continue
        mean, _ = success_rate_with_se(seed_lists)
        out.setdefault(bench, {})[agent] = mean
    # Compute deltas
    for bench, agents in out.items():
        baseline_mean = agents.get(baseline_agent, 0.0)
        out[bench] = {
            agent: {"mean": m, "delta_vs_full": m - baseline_mean}
            for agent, m in agents.items()
        }
    return out


def build_table_reuse(by_cell: Dict[tuple, List[List[dict]]]) -> Dict[str, Any]:
    """Table 4: chaeshin-specific operational metrics (full vs no-cascade)."""
    out: Dict[str, Any] = {}
    for (bench, agent), seed_lists in by_cell.items():
        if not agent.startswith("chaeshin_"):
            continue
        all_records: List[dict] = [r for seed_list in seed_lists for r in seed_list]
        case_counts = [int((r.get("extras", {}) or {}).get("case_bank_size_after", 0))
                       for r in all_records]
        mean_cases = (sum(case_counts) / len(case_counts)) if case_counts else 0.0
        out.setdefault(bench, {})[agent] = {
            "mean_case_bank_size": mean_cases,
            "cross_task_reuse_rate": cross_task_reuse_rate(all_records),
            "stale_reference_rate": stale_reference_rate(all_records),
        }
    return out


def build_table_passk(by_cell: Dict[tuple, List[List[dict]]],
                      ks: List[int] = (1, 4, 8)) -> Dict[str, Any]:
    """Table 5: pass^k (only meaningful when trials_per_task ≥ k)."""
    out: Dict[str, Any] = {}
    for (bench, agent), seed_lists in by_cell.items():
        all_records: List[dict] = [r for seed_list in seed_lists for r in seed_list]
        out.setdefault(bench, {})[agent] = {
            f"pass^{k}": pass_at_k(all_records, k=k) for k in ks
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default="experiments/logs",
                    help="Directory containing *.jsonl run logs")
    ap.add_argument("--output", default="experiments/results/tables.json")
    args = ap.parse_args()

    log_dir = Path(args.logs)
    if not log_dir.exists():
        sys.exit(f"[ERROR] log dir does not exist: {log_dir}")

    by_cell = _scan_logs(log_dir)
    if not by_cell:
        sys.exit(f"[ERROR] no JSONL records under {log_dir}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tables = {
        "table2_main": build_table_main(by_cell),
        "table3_ablation": build_table_ablation(by_cell),
        "table4_reuse": build_table_reuse(by_cell),
        "table5_passk": build_table_passk(by_cell),
        "_meta": {
            "n_cells": len(by_cell),
            "cells": [{"benchmark": b, "agent": a} for (b, a) in sorted(by_cell.keys())],
        },
    }
    out_path.write_text(json.dumps(tables, indent=2, ensure_ascii=False))
    print(f"[written] {out_path}")
    print(json.dumps(tables, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
