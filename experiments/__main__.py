"""Allow `python -m experiments` to print a quick help banner.

For actual runs use the submodules directly:
    python -m experiments.runner       # one cell
    python -m experiments.run_matrix   # full grid
    python -m experiments.aggregate    # logs → tables.json
    python -m experiments.to_latex     # tables.json → \\newcommand macros
"""

from __future__ import annotations

import sys

from experiments.agents import list_agents


_BANNER = """\
chaeshin paper experiments harness
==================================

Common commands:
  python -m experiments.runner --benchmark mock --agent react --seeds 0 --limit 1
  python -m experiments.run_matrix --config experiments/configs/sanity.yaml
  python -m experiments.aggregate
  python -m experiments.to_latex

Available agents:
  {agents}

Available benchmarks:
  mock        (local, no external deps)
  alfworld    (pip install alfworld textworld)
  webshop     (clone princeton-nlp/WebShop)
  taubench    (pip install tau-bench)

See experiments/README.md for the full reproduction guide.
"""


def main():
    sys.stdout.write(_BANNER.format(agents="  ".join(list_agents())))


if __name__ == "__main__":
    main()
