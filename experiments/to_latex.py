"""Convert aggregate results JSON → LaTeX table replacements for paper.

Reads `tables.json` produced by `aggregate.py` and emits paper-ready
table cells. The intended workflow:

    uv run python -m experiments.runner ...           # run experiments
    uv run python -m experiments.aggregate            # → results/tables.json
    uv run python -m experiments.to_latex             # → results/tables_inline.tex

Then in `paper/`:
    sed -i 's/\\\\pred{82.1}/82.1/g' chaeshin.tex      # remove red on real numbers
    OR: include results/tables_inline.tex directly via \\input

The script writes `tables_inline.tex` as a flat list of macros:
    \\newcommand{\\resAlfworldChaeshin}{82.1 $\\pm$ 1.3}
which the paper can then reference inline:
    Chaeshin reaches \\resAlfworldChaeshin\\% on ALFWorld.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict


def _macro_name(*parts: str) -> str:
    """Build a CamelCase LaTeX macro name from parts.

    Letters only (LaTeX restriction). Strip non-letters.
    """
    chunks = []
    for p in parts:
        # Replace digits/special with words
        p = (p.replace("1", "One").replace("2", "Two").replace("3", "Three")
              .replace("4", "Four").replace("5", "Five").replace("6", "Six")
              .replace("7", "Seven").replace("8", "Eight").replace("9", "Nine")
              .replace("0", "Zero").replace("_", "").replace("-", ""))
        p = re.sub(r"[^A-Za-z]", "", p)
        chunks.append(p[:1].upper() + p[1:] if p else "")
    return "res" + "".join(chunks)


def _fmt_pct(x: float, se: float = 0.0) -> str:
    if se > 0:
        return f"{x*100:.1f} $\\pm$ {se*100:.1f}"
    return f"{x*100:.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="experiments/results/tables.json")
    ap.add_argument("--output", default="experiments/results/tables_inline.tex")
    args = ap.parse_args()

    tables = json.loads(Path(args.input).read_text())
    lines: list[str] = [
        "% Auto-generated from experiments/results/tables.json — do not edit by hand.",
        "% Run `uv run python -m experiments.to_latex` to regenerate.",
        "",
    ]

    # Table 2: per (bench, agent) success rate
    for bench, agents in tables.get("table2_main", {}).items():
        for agent, stats in agents.items():
            macro = _macro_name(bench, agent)
            lines.append(f"\\newcommand{{\\{macro}}}{{{_fmt_pct(stats['mean'], stats.get('se', 0))}}}")

    # Table 4: chaeshin reuse metrics
    for bench, agents in tables.get("table4_reuse", {}).items():
        for agent, stats in agents.items():
            macroN  = _macro_name(bench, agent, "BankSize")
            macroR  = _macro_name(bench, agent, "ReuseRate")
            macroS  = _macro_name(bench, agent, "StaleRate")
            lines.append(f"\\newcommand{{\\{macroN}}}{{{stats['mean_case_bank_size']:.0f}}}")
            lines.append(f"\\newcommand{{\\{macroR}}}{{{stats['cross_task_reuse_rate']*100:.1f}\\%}}")
            lines.append(f"\\newcommand{{\\{macroS}}}{{{stats['stale_reference_rate']*100:.1f}\\%}}")

    # Table 5: pass^k
    for bench, agents in tables.get("table5_passk", {}).items():
        for agent, stats in agents.items():
            for k_label, value in stats.items():
                k = k_label.split("^")[1]
                macro = _macro_name(bench, agent, "PassK", k)
                lines.append(f"\\newcommand{{\\{macro}}}{{{value*100:.1f}}}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"[written] {out}")
    print(f"  {len(lines) - 3} macros emitted")


if __name__ == "__main__":
    main()
