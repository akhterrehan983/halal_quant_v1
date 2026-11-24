"""OHLCV validation for ingestion and quality reports."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from app.market_data.calendar import detect_missing_sessions
from app.market_data.schemas import CandleRow, ValidationIssue, ValidationReport


def _finite(x: float) -> bool:
    return math.isfinite(x)


def validate_ohlc_row(row: pd.Series, row_index: int) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    sym = str(row.get("symbol", ""))
    td = row["date"].date() if hasattr(row["date"], "date") else row["date"]

    fields = ["open", "high", "low", "close"]
    for f in fields:
        val = row[f]
        if pd.isna(val) or not _finite(float(val)):
            issues.append(
                ValidationIssue(
                    level="error",
                    code="invalid_numeric",
                    message=f"{f} must be a finite number",
                    symbol=sym,
                    trading_date=td,
                    row_index=row_index,
                )
            )
        elif float(val) <= 0:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="non_positive_price",
                    message=f"{f} must be positive",
                    symbol=sym,
                    trading_date=td,
                    row_index=row_index,
                )
            )

    vol = row["volume"]
    if pd.isna(vol) or int(vol) < 0:
        issues.append(
            ValidationIssue(
                level="error",
                code="invalid_volume",
                message="Volume must be non-negative",
                symbol=sym,
                trading_date=td,
                row_index=row_index,
            )
        )

    if len([i for i in issues if i.level == "error"]) == 0:
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
        if h < l:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="ohlc_inconsistent",
                    message="High must be >= low",
                    symbol=sym,
                    trading_date=td,
                    row_index=row_index,
                )
            )
        elif h < max(o, c) or l > min(o, c):
            issues.append(
                ValidationIssue(
                    level="error",
                    code="ohlc_inconsistent",
                    message="High/low must bracket open and close",
                    symbol=sym,
                    trading_date=td,
                    row_index=row_index,
                )
            )
    return issues


def detect_outliers(df: pd.DataFrame) -> list[ValidationIssue]:
    """Flag suspicious moves; never auto-delete."""
    warnings: list[ValidationIssue] = []
    for symbol, grp in df.groupby("symbol"):
        g = grp.sort_values("date")
        if len(g) < 2:
            continue
        ret = g["close"].pct_change()
        vol_ratio = g["volume"] / g["volume"].rolling(20, min_periods=5).mean()
        for idx, r in ret.items():
            if pd.isna(r):
                continue
            if abs(r) > 0.25:
                row = g.loc[idx]
                warnings.append(
                    ValidationIssue(
                        level="warning",
                        code="price_outlier",
                        message=f"Large daily return {r:.1%} — review before trusting",
                        symbol=symbol,
                        trading_date=row["date"].date(),
                    )
                )
        for idx, vr in vol_ratio.items():
            if pd.notna(vr) and vr > 8:
                row = g.loc[idx]
                warnings.append(
                    ValidationIssue(
                        level="warning",
                        code="volume_outlier",
                        message=f"Relative volume spike {vr:.1f}x — review",
                        symbol=symbol,
                        trading_date=row["date"].date(),
                    )
                )
    return warnings


def validate_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, ValidationReport]:
    report = ValidationReport()
    dup_mask = df.duplicated(subset=["symbol", "date"], keep=False)
    report.duplicate_rows_in_file = int(dup_mask.sum())
    if report.duplicate_rows_in_file:
        for idx in df.index[dup_mask]:
            row = df.loc[idx]
            report.issues.append(
                ValidationIssue(
                    level="error",
                    code="duplicate_in_file",
                    message="Duplicate symbol/date in CSV",
                    symbol=row["symbol"],
                    trading_date=row["date"].date(),
                    row_index=int(idx),
                )
            )

    valid_frames = []
    for idx, row in df.iterrows():
        row_issues = validate_ohlc_row(row, int(idx))
        errors = [i for i in row_issues if i.level == "error"]
        if errors:
            report.issues.extend(errors)
            report.rejected_rows += 1
            continue
        report.valid_rows += 1
        valid_frames.append(row)

    valid_df = pd.DataFrame(valid_frames) if valid_frames else pd.DataFrame(columns=df.columns)
    valid_df = valid_df.drop_duplicates(subset=["symbol", "date"], keep="first")

    report.outliers = detect_outliers(valid_df)
    report.warnings.extend(report.outliers)

    for symbol, grp in valid_df.groupby("symbol"):
        dates = [d.date() if hasattr(d, "date") else d for d in grp["date"].tolist()]
        missing, approximate = detect_missing_sessions(dates)
        if missing:
            report.missing_sessions[symbol] = missing[:120]  # cap payload
        report.missing_sessions_approximate = approximate

    return valid_df, report


def rows_to_candles(df: pd.DataFrame) -> list[CandleRow]:
    candles: list[CandleRow] = []
    for row in df.itertuples():
        td = row.date.date() if hasattr(row.date, "date") else row.date
        candles.append(
            CandleRow(
                symbol=row.symbol,
                trading_date=td,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=int(row.volume),
            )
        )
    return candles