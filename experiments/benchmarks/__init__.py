"""Benchmark registry — single point of lookup for runner."""

from experiments.benchmarks.base import Benchmark, Environment, Outcome, Task, ToolSpec
from experiments.benchmarks.mock_adapter import MockBenchmark


def get_benchmark(name: str, **kwargs) -> Benchmark:
    """Lazy registry — imports a benchmark only when requested.

    External benchmarks (alfworld/webshop/taubench) have heavy
    dependencies, so we don't import them at module load.
    """
    name = name.lower()
    if name == "mock":
        return MockBenchmark(**kwargs)
    if name == "alfworld":
        from experiments.benchmarks.alfworld_adapter import AlfworldBenchmark
        return AlfworldBenchmark(**kwargs)
    if name == "webshop":
        from experiments.benchmarks.webshop_adapter import WebshopBenchmark
        return WebshopBenchmark(**kwargs)
    if name == "taubench":
        from experiments.benchmarks.taubench_adapter import TauBenchBenchmark
        return TauBenchBenchmark(**kwargs)
    raise ValueError(f"unknown benchmark: {name!r}")


__all__ = [
    "Benchmark", "Environment", "Outcome", "Task", "ToolSpec",
    "get_benchmark",
]
