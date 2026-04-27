"""Single-config experiment runner.

One invocation = one (benchmark, agent, seed) cell of the experimental
matrix. Iterates through every task, runs the agent, writes one JSONL
line per (task, trial) tuple to logs/<run_name>.jsonl.

Usage:
    uv run python -m experiments.runner \\
        --benchmark mock --agent react --seeds 0,1,2 \\
        --output logs/

    uv run python -m experiments.runner \\
        --benchmark alfworld --agent chaeshin_full \\
        --seeds 0 --limit 20 --max-steps 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from experiments.agents import get_agent, list_agents
from experiments.benchmarks import get_benchmark


def _build_adapter(model: str = "gpt-4o-mini"):
    """Lazy import so non-OpenAI runs don't pay the dep cost."""
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("[ERROR] OPENAI_API_KEY missing. Set it or use a .env file.")
    from chaeshin.integrations.openai import OpenAIAdapter
    return OpenAIAdapter(model=model, temperature=0.1)


def _record_to_jsonl(record, benchmark_name: str, task_id: str, seed: int, trial_idx: int) -> str:
    record.benchmark_name = benchmark_name
    record.task_id = task_id
    record.seed = seed
    record.trial_idx = trial_idx
    return json.dumps(asdict(record), ensure_ascii=False)


async def _run_one_seed(
    *,
    benchmark_name: str,
    agent_name: str,
    seed: int,
    limit: Optional[int],
    max_steps: int,
    model: str,
    output_path: Path,
    trials_per_task: int = 1,
) -> Dict[str, Any]:
    random.seed(seed)
    bench = get_benchmark(benchmark_name, limit=limit)
    agent = get_agent(agent_name)
    adapter = _build_adapter(model=model)

    n_tasks = 0
    n_success = 0
    t_start = time.time()

    with output_path.open("a", encoding="utf-8") as f:
        for task in bench.tasks():
            for trial in range(trials_per_task):
                env = bench.make_env(task)
                try:
                    record = await agent.run(env, adapter, max_steps=max_steps)
                except Exception as e:
                    sys.stderr.write(
                        f"[WARN] {benchmark_name}/{agent_name}/seed{seed}/{task.task_id}/t{trial}: "
                        f"{type(e).__name__}: {e}\n"
                    )
                    continue
                line = _record_to_jsonl(record, benchmark_name, task.task_id, seed, trial)
                f.write(line + "\n")
                f.flush()
                n_tasks += 1
                if record.success:
                    n_success += 1

    elapsed = time.time() - t_start
    return {
        "benchmark": benchmark_name,
        "agent": agent_name,
        "seed": seed,
        "n_tasks": n_tasks,
        "n_success": n_success,
        "success_rate": n_success / max(1, n_tasks),
        "elapsed_seconds": elapsed,
    }


def main():
    ap = argparse.ArgumentParser(description="Chaeshin paper experiment runner.")
    ap.add_argument("--benchmark", required=True,
                    help="One of: mock, alfworld, webshop, taubench")
    ap.add_argument("--agent", required=True,
                    help="One of: " + ", ".join(list_agents()))
    ap.add_argument("--seeds", default="0",
                    help="Comma-separated seed list (default: 0)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap tasks per seed (useful for sanity)")
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--trials-per-task", type=int, default=1,
                    help="For pass^k experiments — runs each task this many times")
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--output", default="experiments/logs",
                    help="Directory to write JSONL logs")
    args = ap.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries: List[Dict[str, Any]] = []
    for seed in seeds:
        run_name = f"{args.benchmark}__{args.agent}__seed{seed}.jsonl"
        out_path = out_dir / run_name
        # Truncate any prior partial run
        out_path.write_text("")
        print(f"[run] {run_name}")
        summary = asyncio.run(_run_one_seed(
            benchmark_name=args.benchmark,
            agent_name=args.agent,
            seed=seed,
            limit=args.limit,
            max_steps=args.max_steps,
            model=args.model,
            output_path=out_path,
            trials_per_task=args.trials_per_task,
        ))
        summaries.append(summary)
        print(f"  → {summary['n_success']}/{summary['n_tasks']} = "
              f"{summary['success_rate']:.3f}  in {summary['elapsed_seconds']:.1f}s")

    # Print rollup
    print("\n=== summary ===")
    for s in summaries:
        print(json.dumps(s, ensure_ascii=False))


if __name__ == "__main__":
    main()
