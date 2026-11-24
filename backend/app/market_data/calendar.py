"""NSE trading calendar abstraction (weekdays; holiday set approximate)."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

# Common NSE holidays (partial, extend via licensed calendar later). Used only as hints.
_NSE_HOLIDAYS_APPROXIMATE: set[date] = {
    # 2024 sample subset — not authoritative
    date(2024, 1, 26),
    date(2024, 3, 8),
    date(2024, 3, 25),
    date(2024, 3, 29),
    date(2024, 4, 11),
    date(2024, 4, 17),
    date(2024, 5, 1),
    date(2024, 6, 17),
    date(2024, 7, 17),
    date(2024, 8, 15),
    date(2024, 10, 2),
    date(2024, 11, 1),
    date(2024, 11, 15),
    date(2024, 12, 25),
}


def is_weekday(d: date) -> bool:
    return d.weekday() < 5


def expected_trading_days(start: date, end: date, *, use_holiday_hints: bool = True) -> list[date]:
    """Business weekdays; optional approximate holiday exclusion."""
    days = pd.bdate_range(start=start, end=end, freq="C").date
    out = list(days)
    if use_holiday_hints:
        out = [d for d in out if d not in _NSE_HOLIDAYS_APPROXIMATE]
    return out


def detect_missing_sessions(
    present_dates: list[date],
    *,
    use_holiday_hints: bool = True,
) -> tuple[list[str], bool]:
    """Return ISO date strings of likely missing weekdays in range (approximate)."""
    if not present_dates:
        return [], True
    present = set(present_dates)
    start, end = min(present_dates), max(present_dates)
    expected = expected_trading_days(start, end, use_holiday_hints=use_holiday_hints)
    missing = [d.isoformat() for d in expected if d not in present]
    return missing, True  # always approximate without licensed calendar