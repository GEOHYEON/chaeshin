# Chaeshin paper experiments

Reproduce the empirical results in §6 of `paper/chaeshin.tex`. The harness
runs (benchmark × agent × seed) cells, writes one JSONL line per (task,
trial), then aggregates into the LaTeX macros that the paper consumes.

```
benchmarks ─┐
agents ─────┼──> runner.py ──> logs/*.jsonl ──> aggregate.py ──> tables.json
seeds ──────┘                                                       │
                                                                     ▼
                                                              to_latex.py
                                                                     │
                                                                     ▼
                                                       results/tables_inline.tex
                                                              (paper \input)
```

The numbers shown in red (`\pred{...}`) in the paper are placeholders.
Once you run this harness, `to_latex.py` emits real `\newcommand` macros
that overwrite them.

---

## 0. One-time setup

From the repo root (`chaeshin/`):

```bash
# core deps (chaeshin itself + openai)
uv sync

# experiment-specific deps
uv pip install -r experiments/requirements.txt

# OpenAI key
echo 'OPENAI_API_KEY=sk-...' > .env
```

Sanity check (no external benchmarks needed, ~$0.02):

```bash
uv run python -m experiments.runner \
    --benchmark mock --agent react --seeds 0 --limit 1
```

You should see one JSONL line in `experiments/logs/mock__react__seed0.jsonl`.

---

## 1. Benchmarks

| name       | install                                                     | tasks | est. cost (gpt-4o-mini, full) |
|------------|-------------------------------------------------------------|-------|-------------------------------|
| `mock`     | none — bundled                                              | 3     | <$0.10                        |
| `alfworld` | `pip install alfworld textworld` + `alfworld-download`      | 134   | ~$10                          |
| `webshop`  | `git clone https://github.com/princeton-nlp/WebShop && pip install -e WebShop` | 100 | ~$8 |
| `taubench` | `pip install tau-bench` (or `git+https://github.com/sierra-research/tau-bench`) | 115 | ~$15 |

Each external benchmark is **lazy-imported** in `experiments/benchmarks/__init__.py`,
so missing deps don't break the mock smoke test.

### What each adapter exposes

All adapters implement `experiments.benchmarks.base.Benchmark`:

- `tasks()` — iterator of `Task(task_id, description, metadata)`
- `make_env(task)` — fresh `Environment` per trial. The env exposes:
  - `.observation()` — current state, str
  - `.tools()` — list of `ToolSpec(name, description, schema)`
  - `.step(tool_name, **args)` — returns `Outcome(observation, success, done, info)`
  - `.reset()`

The agent never sees benchmark-specific code; it just calls tools.

---

## 2. Agents

`experiments/agents/__init__.py` exposes 8 agents:

| name                       | description                                                | memory across tasks |
|----------------------------|------------------------------------------------------------|---------------------|
| `react`                    | vanilla ReAct (Thought/Action/Observation)                 | none                |
| `reflexion`                | ReAct + verbal self-reflection between trials              | per-task transcript |
| `voyager_style`            | flat skill library, Jaccard retrieval                      | shared              |
| `adapt`                    | as-needed decomposition (decompose pseudo-tool)            | none                |
| `chaeshin_full`            | retrieve → revise → retain with all 3 mechanisms           | shared SQLite       |
| `chaeshin_no_cascade`      | ablation: revise without orphan invalidation               | shared SQLite       |
| `chaeshin_no_pending`      | ablation: outcomes are binary (success/failure only)       | shared SQLite       |
| `chaeshin_no_recursion`    | ablation: flat case structure (no parent_node_id)          | shared SQLite       |

Each chaeshin variant gets a fresh tempdir SQLite per `--seeds` value, so
seeds remain independent while cases persist *across tasks within one seed*
— that's what we measure as cross-task reuse.

---

## 3. Running the matrix

### Sanity (≈ 8 minutes, < $2)

```bash
uv run python -m experiments.run_matrix \
    --config experiments/configs/sanity.yaml
```

Mock benchmark only, 3 tasks × 8 agents × 1 seed.

### Full main results — Tables 2 & 3 (≈ $216, ~24 h on one machine)

```bash
uv run python -m experiments.run_matrix \
    --config experiments/configs/matrix.yaml
```

3 benchmarks × 8 agents × 3 seeds = 72 cells. Use `--continue-on-error`
to avoid losing the matrix if one cell crashes mid-run.

To run cells in parallel across machines, just sub-shard `agents:` and
`benchmarks:` in the YAML — runner output names are deterministic
(`{benchmark}__{agent}__seed{n}.jsonl`), so they merge by file copy.

### pass^8 — Table 5 (≈ $96)

```bash
uv run python -m experiments.run_matrix \
    --config experiments/configs/passk_taubench.yaml
```

Only τ-bench, only 4 systems, but `trials_per_task: 8`. This is the data
that produces the pass^k consistency gap.

### Single cell

```bash
uv run python -m experiments.runner \
    --benchmark alfworld --agent chaeshin_full \
    --seeds 0,1,2 --max-steps 30 --limit 30
```

---

## 4. Aggregation → paper macros

```bash
# 1. logs/*.jsonl → results/tables.json
uv run python -m experiments.aggregate \
    --logs experiments/logs --output experiments/results/tables.json

# 2. tables.json → \newcommand{\res...} macros
uv run python -m experiments.to_latex \
    --input experiments/results/tables.json \
    --output experiments/results/tables_inline.tex

# 3. wire into paper
cd ../paper
echo '\input{../chaeshin/experiments/results/tables_inline.tex}' >> chaeshin.tex
# ...then replace \pred{82.1\%} with \resAlfworldChaeshin\% in the prose.
```

Generated macro names follow `_macro_name()` in `to_latex.py`:
benchmark + agent + (optional suffix), CamelCase, digits spelled out.
Example: `\resAlfworldChaeshinFullPassKEight` for ALFWorld pass^8.

---

## 5. Layout

```
experiments/
├── __init__.py
├── __main__.py             # python -m experiments → help banner
├── README.md               # ← this file
├── requirements.txt
│
├── benchmarks/
│   ├── base.py             # Benchmark / Environment / Task / Outcome / ToolSpec
│   ├── mock_adapter.py     # 3-task local sanity benchmark
│   ├── alfworld_adapter.py
│   ├── webshop_adapter.py
│   ├── taubench_adapter.py
│   └── __init__.py         # lazy registry
│
├── agents/
│   ├── base.py             # Agent / RunRecord / StepRecord
│   ├── _react_core.py      # shared Thought/Action/Observation loop
│   ├── react_agent.py
│   ├── reflexion_agent.py
│   ├── voyager_style_agent.py
│   ├── adapt_agent.py
│   ├── chaeshin_agent.py   # 4 variants gated by _ChaeshinConfig
│   └── __init__.py
│
├── metrics/
│   ├── success_rate.py     # mean ± std error across seeds
│   ├── pass_at_k.py        # τ-bench pass^k formula
│   ├── stale_reference.py  # chaeshin-specific: dangling parent_node_id
│   └── __init__.py
│
├── configs/
│   ├── sanity.yaml         # smoke test (~$2)
│   ├── matrix.yaml         # paper Tables 2-3 (~$216)
│   └── passk_taubench.yaml # paper Table 5 (~$96)
│
├── runner.py               # one (benchmark, agent, seed) cell
├── run_matrix.py           # YAML config → spawn runner per cell
├── aggregate.py            # JSONL → tables.json
├── to_latex.py             # tables.json → \newcommand macros
│
├── logs/                   # JSONL output (gitignored)
├── results/                # tables.json + tables_inline.tex
└── scripts/                # ad hoc helpers
```

---

## 6. JSONL schema

Each line emitted by `runner.py` is one trial:

```jsonc
{
  "agent_name": "chaeshin_full",
  "benchmark_name": "alfworld",
  "task_id": "pick_and_place_simple-Pillow-None-...",
  "seed": 0,
  "trial_idx": 0,
  "success": true,
  "n_steps": 14,
  "elapsed_seconds": 18.3,
  "transcript": [ {"step": 0, "thought": "...", "tool": "...", "args": {...}, "obs": "..."}, ... ],
  "extras": {
    "case_bank_size_after": 27,
    "retrieved_case_ids": ["a1b2..."],
    "stale_refs_observed": 0,
    "cross_task_reuse": true
  }
}
```

`aggregate.py` reads only the top-level fields plus `extras`; if you add
new metrics, extend `experiments/metrics/` and `aggregate.py` together.

---

## 7. Troubleshooting

- **`OPENAI_API_KEY missing`** → set in `.env` at repo root, or `export` it.
- **`alfworld` import fails** → did you run `alfworld-download`? It needs ~1.5 GB.
- **Cell hangs on τ-bench** → some tasks expect interactive user replies;
  set `--max-steps 30` and check `extras.timeout` in the JSONL.
- **Numbers in `tables.json` look off by a factor of 100** → `to_latex.py`
  multiplies success rate by 100 once. Don't multiply again in the paper.
- **chaeshin SQLite errors with `database is locked`** → only one runner
  per (agent_name, seed) at a time. Use distinct seeds to parallelize.

---

## 8. Cost summary (gpt-4o-mini, March 2026 prices)

| config              | cells | tasks/cell | trials | est. \$  |
|---------------------|-------|-----------|--------|----------|
| `sanity.yaml`       | 8     | 3         | 1      | <\$2     |
| `matrix.yaml`       | 72    | ~30       | 1      | ~\$216   |
| `passk_taubench.yaml` | 4   | 30        | 8      | ~\$96    |
| **Total for paper** | —     | —         | —      | **~\$320** |

Switch `model: gpt-4o-mini` → `gpt-4o` to roughly 10× the cost.
The paper reports gpt-4o-mini numbers because variance across model
versions is the dominant noise source above that price point.
