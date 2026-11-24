from __future__ import annotations

from datetime import date

from app.shariah.eligibility import evaluate_for_standard
from app.shariah.policies import DEFAULT_PROFILE, get_profile
from app.shariah.schemas import EligibilityRecord, EligibilityStatus, PolicyMode
from app.shariah.snapshots import append_snapshot
from app.shariah.standards import BUILTIN_STANDARDS
from app.shariah.store import get_financials, get_latest_eligibility, save_eligibility


def combine_standards(records: list[EligibilityRecord], policy: PolicyMode, primary_id: str | None) -> EligibilityRecord:
    if not records:
        raise ValueError("No records")
    if policy == PolicyMode.PRIMARY and primary_id:
        for r in records:
            if r.standard_id == primary_id:
                return r
    if policy == PolicyMode.ANY_STANDARD:
        for r in records:
            if r.status == EligibilityStatus.COMPLIANT:
                return r
        return records[0]
    # ALL
    if all(r.status == EligibilityStatus.COMPLIANT for r in records):
        base = records[0].model_copy()
        base.explanation = "All selected standards passed"
        return base
    base = records[0].model_copy()
    base.status = EligibilityStatus.NON_COMPLIANT
    base.explanation = "Not all standards passed"
    return base


def run_screening(
    symbol: str,
    *,
    profile_id: str = "default",
    financials: dict | None = None,
    as_of: date | None = None,
) -> EligibilityRecord:
    profile = get_profile(profile_id) or DEFAULT_PROFILE
    fin = financials if financials is not None else get_financials(symbol)
    records: list[EligibilityRecord] = []
    for sid in profile.standard_ids:
        std = BUILTIN_STANDARDS.get(sid)
        if not std:
            continue
        records.append(evaluate_for_standard(symbol, std, financials=fin, as_of=as_of))
    combined = combine_standards(records, profile.policy, profile.primary_standard_id)
    save_eligibility(combined)
    append_snapshot(combined)
    return combined


def eligibility_for_order(symbol: str) -> tuple[bool, list[str]]:
    rec = get_latest_eligibility(symbol)
    if not rec:
        return False, ["No screening on file — evaluate screening first"]
    if rec.status == EligibilityStatus.COMPLIANT:
        if rec.next_review_date and rec.next_review_date < date.today():
            return False, ["Screening expired — re-evaluate required"]
        return True, []
    if rec.status == EligibilityStatus.EXPIRED:
        return False, ["Screening expired"]
    return False, [f"Shariah status {rec.status}: {rec.explanation}"]