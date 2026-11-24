from __future__ import annotations

from decimal import Decimal

from app.portfolio.money import D
from app.shariah.schemas import RatioDetail
from app.shariah.standards import ScreeningStandard


def ratio_result(value: Decimal | None, threshold: Decimal | None, *, higher_is_bad: bool = True) -> str:
    if value is None or threshold is None:
        return "UNKNOWN"
    if threshold == 0:
        return "UNKNOWN"
    if higher_is_bad:
        return "PASS" if value <= threshold else "FAIL"
    return "PASS" if value >= threshold else "FAIL"


def compute_ratios(symbol: str, financials: dict | None, standard: ScreeningStandard) -> list[RatioDetail]:
    if not financials:
        return [
            RatioDetail(
                name="interest_bearing_debt_ratio",
                result="UNKNOWN",
                data_source=None,
            )
        ]
    src = financials.get("data_source", "user_supplied")
    period = financials.get("reporting_period")
    debt = financials.get("interest_bearing_debt")
    mcap = financials.get("market_capitalization")
    assets = financials.get("total_assets")
    denom = D(mcap) if mcap else (D(assets) if assets else None)
    debt_ratio = None
    if debt is not None and denom and denom > 0:
        debt_ratio = (D(debt) / denom).quantize(Decimal("0.0001"))
    nc_income = financials.get("non_compliant_income")
    revenue = financials.get("revenue")
    nc_ratio = None
    if nc_income is not None and revenue and D(revenue) > 0:
        nc_ratio = (D(nc_income) / D(revenue)).quantize(Decimal("0.0001"))

    ratios: list[RatioDetail] = [
        RatioDetail(
            name="interest_bearing_debt_ratio",
            numerator=D(debt) if debt is not None else None,
            denominator=denom,
            value=debt_ratio,
            threshold=standard.debt_ratio_max,
            result=ratio_result(debt_ratio, standard.debt_ratio_max),
            reporting_period=period,
            data_source=src,
        ),
        RatioDetail(
            name="non_compliant_income_ratio",
            numerator=D(nc_income) if nc_income is not None else None,
            denominator=D(revenue) if revenue is not None else None,
            value=nc_ratio,
            threshold=standard.non_compliant_income_max,
            result=ratio_result(nc_ratio, standard.non_compliant_income_max),
            reporting_period=period,
            data_source=src,
        ),
    ]
    if standard.cash_receivables_max is not None:
        cash = financials.get("cash_and_equivalents")
        recv = financials.get("receivables")
        tot = (D(cash or 0) + D(recv or 0)) if cash is not None or recv is not None else None
        cr_ratio = (tot / denom).quantize(Decimal("0.0001")) if tot is not None and denom and denom > 0 else None
        ratios.append(
            RatioDetail(
                name="cash_receivables_to_market_cap",
                numerator=tot,
                denominator=denom,
                value=cr_ratio,
                threshold=standard.cash_receivables_max,
                result=ratio_result(cr_ratio, standard.cash_receivables_max),
                reporting_period=period,
                data_source=src,
            )
        )
    return ratios


def ratios_pass(ratios: list[RatioDetail]) -> bool:
    known = [r for r in ratios if r.result in ("PASS", "FAIL")]
    if not known:
        return False
    return all(r.result == "PASS" for r in known)