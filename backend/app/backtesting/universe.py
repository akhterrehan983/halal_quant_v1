"""Point-in-time universe provider — current demo symbols with survivorship warning."""

from __future__ import annotations

from datetime import date

from app.market_data.repository import iter_symbol_histories, list_universe_symbols


class UniverseSnapshot:
    def __init__(self, as_of: date, symbols: list[str], *, survivorship_warning: bool):
        self.as_of = as_of
        self.symbols = symbols
        self.survivorship_warning = survivorship_warning

    def to_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "symbols": self.symbols,
            "survivorship_warning": self.survivorship_warning,
            "mode": "current_snapshot_with_survivorship_warning",
        }


def universe_for_backtest(start: date, end: date, explicit: list[str] | None) -> tuple[UniverseSnapshot, list[str]]:
    warning = True
    if explicit:
        return UniverseSnapshot(end, [s.upper() for s in explicit], survivorship_warning=warning), explicit
    symbols = list_universe_symbols()
    snap = UniverseSnapshot(end, symbols, survivorship_warning=warning)
    return snap, symbols


def symbols_with_data(symbols: list[str], start: date, end: date) -> list[str]:
    out = []
    for sym, df in iter_symbol_histories():
        if sym not in symbols:
            continue
        dates = __import__("pandas").to_datetime(df["date"]).dt.date
        if dates.min() <= start and dates.max() >= end:
            out.append(sym)
    return out or [s for s in symbols if s in dict(iter_symbol_histories())]