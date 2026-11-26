"""Explicit benchmark / index-proxy registry (M14 Phase 1.1, finding F-3).

A registered benchmark is a reference series (regime, relative strength, benchmark-relative metrics).
It is never an equity: it must not be scanned for signals, counted in breadth, or traded.

The registry is the single source of truth. Built-in entries live here; further symbols can be
registered through the ``BENCHMARK_SYMBOLS`` setting (comma-separated, e.g. ``NIFTY50,NIFTYBANK``).
The result depends only on configuration, never on which runs happened earlier in the process.

Settings are read at call time through the ``app.core.config`` module (not bound at import), so the
test configuration that swaps ``app.core.config.settings`` controls this module too.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import config as _config

DEFAULT_BENCHMARK_SYMBOL = "NIFTY500_PROXY"


@dataclass(frozen=True)
class BenchmarkSpec:
    symbol: str
    kind: str  # "equal_weight_proxy" (built-in) | "configured" (from BENCHMARK_SYMBOLS)
    description: str


_BUILTIN: tuple[BenchmarkSpec, ...] = (
    BenchmarkSpec(
        symbol=DEFAULT_BENCHMARK_SYMBOL,
        kind="equal_weight_proxy",
        description=(
            "Equal-weight average of the current equity universe (survivor proxy), "
            "or an imported series stored under the same symbol."
        ),
    ),
)


def registered_benchmarks() -> dict[str, BenchmarkSpec]:
    registry = {b.symbol: b for b in _BUILTIN}
    for raw in (_config.settings.benchmark_symbols or "").split(","):
        symbol = raw.strip().upper()
        if symbol and symbol not in registry:
            registry[symbol] = BenchmarkSpec(symbol, "configured", "Registered through BENCHMARK_SYMBOLS.")
    return registry


def benchmark_symbols() -> frozenset[str]:
    return frozenset(registered_benchmarks())


def is_benchmark(symbol: str) -> bool:
    return str(symbol).strip().upper() in registered_benchmarks()
