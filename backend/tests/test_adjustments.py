from datetime import date
from decimal import Decimal

import pandas as pd

from app.market_data.adjustments import apply_adjustments
from app.models.corporate_actions import CorporateAction


def test_raw_unchanged_apply_adjustments_copy():
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=5, freq="B"),
            "close": [100, 101, 102, 103, 104],
        }
    )
    original_close = df["close"].iloc[-1]
    actions = [
        CorporateAction(
            symbol="X",
            action_type="split",
            effective_date=date(2024, 1, 3),
            factor=Decimal("0.5"),
        )
    ]
    adj = apply_adjustments(df, actions)
    assert df["close"].iloc[-1] == original_close
    assert "adjusted_close" in adj.columns
    assert adj["adjusted_close"].iloc[-1] != original_close


def test_no_actions_sets_adjusted_equal_close():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=3, freq="B"), "close": [10, 11, 12]})
    out = apply_adjustments(df, [])
    assert list(out["adjusted_close"]) == list(out["close"])