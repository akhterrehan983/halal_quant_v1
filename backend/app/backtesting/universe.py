"""Point-in-time universe provider — current demo symbols with survivorship warning.

Registered benchmarks / index proxies (``app.market_data.benchmarks``) are partitioned out of every
requested universe: they are reported as excluded and are never scanned or traded as equities.
"""

from __future__ import annotations

from datetime import date

from app.market_data.benchmarks import benchmark_symbols
from app.market_data.repository import iter_symbol_histories, list_all_symbols


class UniverseSnapshot:
    def __init__(
        self,
        as_of: date,
        symbols: list[str],
        *,
        survivorship_warning: bool,
        benchmark_excluded: list[str] | None = None,
    ):
        self.as_of = as_of
        self.symbols = symbols
        self.survivorship_warning = survivorship_warning
        self.benchmark_excluded = benchmark_excluded or []

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "symbols": self.symbols,
            "benchmark_excluded": self.benchmark_excluded,
            "survivorship_warning": self.survivorship_warning,
            "mode": "current_snapshot_with_survivorship_warning",
        }


def partition_universe(candidates: list[str]) -> tuple[list[str], list[str]]:
    """Split ``candidates`` into (tradable equities, excluded registered benchmarks).

    Upper-cases, de-duplicates and keeps the first-seen order of tradable symbols. The result depends
    only on the candidate list and the benchmark registry.
    """
    benchmarks = benchmark_symbols()
    tradable: list[str] = []
    excluded: list[str] = []
    for raw in candidates:
        sym = str(raw).strip().upper()
        if not sym:
            continue
        if sym in benchmarks:
            if sym not in excluded:
                excluded.append(sym)
        elif sym not in tradable:
            tradable.append(sym)
    return tradable, sorted(excluded)


def universe_for_backtest(start: date, end: date, explicit: list[str] | None) -> tuple[UniverseSnapshot, list[str]]:
    """The tradable universe for a run. An explicit list wins; otherwise every stored symbol."""
    requested = list(explicit) if explicit else list_all_symbols()
    tradable, benchmark_excluded = partition_universe(requested)
    snap = UniverseSnapshot(end, tradable, survivorship_warning=True, benchmark_excluded=benchmark_excluded)
    return snap, tradable


def symbols_with_data(symbols: list[str], start: date, end: date) -> list[str]:
    out = []
    for sym, df in iter_symbol_histories():
        if sym not in symbols:
            continue
        dates = __import__("pandas").to_datetime(df["date"]).dt.date
        if dates.min() <= start and dates.max() >= end:
            out.append(sym)
    return out or [s for s in symbols if s in dict(iter_symbol_histories())]
