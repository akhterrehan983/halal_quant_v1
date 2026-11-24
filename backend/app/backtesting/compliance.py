from __future__ import annotations

from datetime import date

from app.backtesting.schemas import ShariahBacktestMode
from app.shariah.schemas import EligibilityStatus
from app.shariah import store as sh_store


def snapshot_as_of(symbol: str, as_of: date) -> tuple[bool, str]:
    snaps = sh_store.list_snapshots(symbol)
    eligible = None
    for s in snaps:
        if s.screening_date <= as_of and s.status == EligibilityStatus.COMPLIANT:
            if s.snapshot_id and (eligible is None or s.screening_date > eligible.screening_date):
                eligible = s
    if eligible:
        return True, f"COMPLIANT snapshot {eligible.screening_date}"
    latest = sh_store.get_latest_eligibility(symbol)
    if latest and latest.verified_at and latest.verified_at <= as_of and latest.status == EligibilityStatus.COMPLIANT:
        return True, "point-in-time eligibility record"
    return False, "no valid point-in-time compliance"


def check_entry(symbol: str, as_of: date, mode: ShariahBacktestMode) -> tuple[bool, str]:
    ok, reason = snapshot_as_of(symbol, as_of)
    if ok:
        return True, reason
    if mode == ShariahBacktestMode.RESEARCH_ONLY:
        return True, "RESEARCH_ONLY — not Shariah-validated"
    return False, reason or "STRICT rejection"