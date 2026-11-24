from decimal import Decimal

import pytest

from app.data.sample_data import make_history
from app.execution.order_manager import create_order
from app.execution.schemas import OrderSide, OrderState, OrderType
from app.portfolio.money import D
from app.shariah.business_activity import submit_activity
from app.shariah.financial_ratios import compute_ratios
from app.shariah.schemas import EligibilityStatus
from app.shariah.screening import run_screening
from app.shariah.standards import BUILTIN_STANDARDS
from app.execution.sell_authorization import evaluate_sell
from app.shariah.schemas import OwnershipPossessionState
from app.execution import store


@pytest.fixture
def compliant_tcs():
    submit_activity(
        "TCS",
        [{"category": "it_services", "prohibited": False, "source": "test_fixture", "verified_at": "2026-01-01"}],
    )
    fin = {
        "data_source": "test_fixture",
        "reporting_period": "FY2025",
        "interest_bearing_debt": 1000,
        "market_capitalization": 100000,
        "non_compliant_income": 100,
        "revenue": 50000,
    }
    return run_screening("TCS", financials=fin)


def test_insufficient_data_without_financials():
    rec = run_screening("UNKNOWNCO")
    assert rec.status in (EligibilityStatus.INSUFFICIENT_DATA, EligibilityStatus.NEEDS_REVIEW)


def test_compliant_with_fixture(compliant_tcs):
    assert compliant_tcs.status == EligibilityStatus.COMPLIANT


def test_ratio_zero_denominator():
    ratios = compute_ratios("X", {"market_capitalization": 0, "interest_bearing_debt": 1}, BUILTIN_STANDARDS["aaoifi_demo_v1"])
    assert any(r.result == "UNKNOWN" for r in ratios)


def test_sell_denied_without_authorization():
    store._STATE = store._empty()  # noqa: SLF001
    auth = evaluate_sell("TCS", 1)
    assert not auth.granted


def test_buy_order_rejected_without_screening():
    store._STATE = store._empty()  # noqa: SLF001
    o = create_order(
        symbol="TCS",
        sleeve="swing",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        proposal_id=None,
    )
    assert o.state == OrderState.REJECTED


def test_api_shariah_standards():
    from fastapi.testclient import TestClient
    from app.main import app

    assert TestClient(app).get("/api/v1/shariah/standards").status_code == 200