"""Run the full benchmark × agent × seed grid.

Reads a YAML config that specifies which cells to run, then launches
each cell via `runner.py`. Useful for the paper's main results
(Tables 2-3) or for reproducing an entire ablation in one command.

Usage:
    uv run python -m experiments.run_matrix --config experiments/configs/matrix.yaml
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def _load_config(path: Path) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError:
        sys.exit("[ERROR] pyyaml not installed. uv pip install pyyaml")
    with path.open() as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="experiments/configs/matrix.yaml")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print commands without running")
    ap.add_argument("--continue-on-error", action="store_true",
                    help="Don't stop the matrix if one cell fails")
    args = ap.parse_args()

    cfg = _load_config(Path(args.config))

    benchmarks: List[str] = cfg.get("benchmarks", [])
    agents: List[str] = cfg.get("agents", [])
    seeds: List[int] = cfg.get("seeds", [0])
    common = {
        "limit": cfg.get("limit"),
        "max_steps": cfg.get("max_steps", 30),
        "trials_per_task": cfg.get("trials_per_task", 1),
        "model": cfg.get("model", "gpt-4o-mini"),
        "output": cfg.get("output", "experiments/logs"),
    }

    cells: List[List[str]] = []
    for b in benchmarks:
        for a in agents:
            cmd = [
                sys.executable, "-m", "experiments.runner",
                "--benchmark", b,
                "--agent", a,
                "--seeds", ",".join(str(s) for s in seeds),
                "--max-steps", str(common["max_steps"]),
                "--trials-per-task", str(common["trials_per_task"]),
                "--model", common["model"],
                "--output", common["output"],
            ]
            if common["limit"]:
                cmd.extend(["--limit", str(common["limit"])])
            cells.append(cmd)

    print(f"Matrix: {len(benchmarks)} benchmarks × {len(agents)} agents = {len(cells)} cells")
    print(f"        seeds={seeds}, limit={common['limit']}, model={common['model']}")
    print()

    failed: List[str] = []
    for i, cmd in enumerate(cells, start=1):
        cmd_str = " ".join(cmd)
        print(f"[{i}/{len(cells)}] {cmd_str}")
        if args.dry_run:
            continue
        rc = subprocess.call(cmd)
        if rc != 0:
            failed.append(cmd_str)
            if not args.continue_on_error:
                sys.exit(f"\n[FAIL] cell {i} returned {rc}; stopping. "
                         f"Use --continue-on-error to skip past failures.")

    if failed:
        print(f"\n[done] {len(cells) - len(failed)}/{len(cells)} succeeded.")
        print("Failed cells:")
        for c in failed:
            print(f"  {c}")
    else:
        print(f"\n[done] all {len(cells)} cells succeeded.")


if __name__ == "__main__":
    main()
