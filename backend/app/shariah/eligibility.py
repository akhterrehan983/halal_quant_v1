from __future__ import annotations

from datetime import date, timedelta

from app.shariah.business_activity import activity_blocks, activity_passes, evaluate_business_activity
from app.shariah.financial_ratios import compute_ratios, ratios_pass
from app.shariah.schemas import EligibilityRecord, EligibilityStatus
from app.shariah.standards import BUILTIN_STANDARDS, ScreeningStandard


def evaluate_for_standard(
    symbol: str,
    standard: ScreeningStandard,
    *,
    financials: dict | None,
    as_of: date | None = None,
) -> EligibilityRecord:
    as_of = as_of or date.today()
    biz = evaluate_business_activity(symbol, standard)
    ratios = compute_ratios(symbol, financials, standard)

    if activity_blocks(biz):
        status = EligibilityStatus.NON_COMPLIANT
        explanation = "Business activity exclusion triggered"
    elif not financials:
        status = EligibilityStatus.INSUFFICIENT_DATA
        explanation = "Financial inputs required for ratio screening"
    elif any(r.result == "FAIL" for r in ratios):
        status = EligibilityStatus.NON_COMPLIANT
        explanation = "One or more financial ratios exceed threshold"
    elif any(r.result == "UNKNOWN" for r in ratios if r.name in ("interest_bearing_debt_ratio", "non_compliant_income_ratio")) or not activity_passes(biz):
        status = EligibilityStatus.NEEDS_REVIEW
        explanation = "Missing or ambiguous activity/ratio data"
    elif activity_passes(biz) and ratios_pass(ratios):
        status = EligibilityStatus.COMPLIANT
        explanation = f"Passes under {standard.standard_id} v{standard.version} (user data)"
    else:
        status = EligibilityStatus.NEEDS_REVIEW
        explanation = "Inconclusive screening"

    verified = as_of
    next_review = as_of + timedelta(days=standard.review_days)
    return EligibilityRecord(
        symbol=symbol.upper(),
        standard_id=standard.standard_id,
        standard_version=standard.version,
        status=status,
        business_activity=biz,
        ratios=ratios,
        effective_date=as_of,
        verified_at=verified,
        next_review_date=next_review,
        explanation=explanation,
        sources=[standard.source_ref],
    )