"""Event-driven historical simulator (M14 Phase 1).

Session order:
  1. Fills: entries whose fill date has arrived, re-validated at the actual fill price.
  2. Exits: stop/target enforcement (stop-first on a bar that hits both) and authorised time exits.
     A stop breached before the sale is authorised is executed at the first authorised session.
  3. Marks: held positions marked at their last known close; stale marks are counted.
     The session equity point is recorded after exits.
  4. Signals: scan the full tradable universe (benchmark excluded) using only bars <= session,
     size at signal time, and queue the top candidate for next-session fill.

Limitations that remain after Phase 1 are documented in docs/m14_backtesting_audit.md.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from app.backtesting.compliance import check_entry
from app.backtesting.costs import buy_cost, sell_cost
from app.backtesting.execution import earliest_sell_date
from app.backtesting.metrics import compute_metrics
from app.backtesting.portfolio import SimBook, SimPosition
from app.backtesting.schemas import (
    BacktestConfig,
    BacktestRun,
    BacktestStatus,
    CompletedTrade,
    DataProvenance,
    EquityPoint,
    EvidenceGrade,
)
from app.backtesting.universe import universe_for_backtest
from app.backtesting.validation import build_validation_report
from app.market_data import repository as repo
from app.market_data.benchmarks import benchmark_symbols
from app.portfolio.money import D, money
from app.portfolio.position_sizing import compute_position_quantity
from app.regime.market_breadth import breadth_cache_scope
from app.risk.limits import DEFAULT_RISK_CONFIG
from app.signals.generator import generate_unified_signal
from app.signals.schemas import SignalCategory

SIGNAL_LOOKBACK_BARS = 520
MIN_SIGNAL_BARS = 60
STALE_LIMIT_SESSIONS = 5
COVERAGE_GAP_DAYS = 5
OWNERSHIP_PENDING_REASON = "stop_ownership_delayed"
PRICE_Q = Decimal("0.01")


@dataclass
class _SymbolFeed:
    """All bars for one symbol up to the backtest end date, with fast as-of lookups."""

    symbol: str
    frame: pd.DataFrame
    dates: list[date]
    source: str
    is_synthetic: bool | None

    def count_upto(self, session: date) -> int:
        return bisect_right(self.dates, session)

    def window(self, session: date, lookback: int) -> pd.DataFrame | None:
        n = self.count_upto(session)
        if n == 0:
            return None
        return self.frame.iloc[max(0, n - lookback) : n]

    def bar_on(self, session: date) -> pd.Series | None:
        n = self.count_upto(session)
        if n and self.dates[n - 1] == session:
            return self.frame.iloc[n - 1]
        return None

    def last_known(self, session: date) -> tuple[pd.Series | None, date | None]:
        n = self.count_upto(session)
        if n == 0:
            return None, None
        return self.frame.iloc[n - 1], self.dates[n - 1]

    def next_bar(self, after: date) -> pd.Series | None:
        n = self.count_upto(after)
        return self.frame.iloc[n] if n < len(self.dates) else None


def _load_feed(symbol: str, end: date) -> _SymbolFeed | None:
    try:
        frame = repo.history_upto(symbol, end=end)
    except repo.SymbolNotFoundError:
        return None
    if frame.empty:
        return None
    dates = pd.to_datetime(frame["date"]).dt.date.tolist()
    try:
        meta = repo.symbol_metadata(symbol)
        source, is_synthetic = str(meta.get("source", "unknown")), bool(meta.get("is_synthetic"))
    except repo.SymbolNotFoundError:
        source, is_synthetic = "unknown", None
    return _SymbolFeed(symbol=symbol, frame=frame, dates=dates, source=source, is_synthetic=is_synthetic)


def _provenance(feeds: dict[str, _SymbolFeed]) -> tuple[DataProvenance, EvidenceGrade]:
    flags = [f.is_synthetic for f in feeds.values()]
    if not flags or any(x is None for x in flags):
        kind = "unknown"
    elif all(flags):
        kind = "synthetic"
    elif not any(flags):
        kind = "imported"
    else:
        kind = "mixed"
    sources = sorted({f.source for f in feeds.values()})
    prov = DataProvenance(
        kind=kind,
        source=", ".join(sources) if sources else "unknown",
        symbols={s: f.source for s, f in feeds.items()},
    )
    grade = EvidenceGrade.IMPORTED_UNVERIFIED if kind == "imported" else EvidenceGrade.DEMO
    return prov, grade


def _mark_price(feed: _SymbolFeed, session: date, pos: SimPosition) -> Decimal:
    row, _ = feed.last_known(session)
    return D(row["close"]) if row is not None else pos.entry_price


def _close_position(
    book: SimBook,
    symbol: str,
    px: Decimal,
    reason: str,
    session: date,
    config: BacktestConfig,
    trades: list[CompletedTrade],
) -> None:
    pos = book.positions.pop(symbol)
    notional = D(pos.quantity) * px
    fees = D(sell_cost(notional, config.cost_scenario)["total"])
    book.cash = money(book.cash + notional - fees)
    book.costs_paid += fees
    net = notional - D(pos.quantity) * pos.entry_price - fees
    book.realized_pnl += net

    # Stop reporting. The fill (px) is the actual fill; loss beyond stop is measured against the stop level.
    delayed = reason == OWNERSHIP_PENDING_REASON
    stop_driven = delayed or reason == "stop"
    breach_date = (pos.stop_breach_date or session) if delayed else (session if stop_driven else None)
    loss_beyond_stop = D(max(D(0), (pos.stop - px) * D(pos.quantity))) if stop_driven else None
    trades.append(
        CompletedTrade(
            symbol=symbol,
            strategy=pos.strategy,
            horizon=config.horizon,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            quantity=pos.quantity,
            exit_date=session,
            exit_price=px,
            gross_pnl=notional - D(pos.quantity) * pos.entry_price,
            net_pnl=net,
            costs=fees,
            holding_days=(session - pos.entry_date).days,
            exit_reason=reason,
            ownership_delayed_exit=delayed,
            signal_quantity=pos.signal_quantity,
            stop_price=pos.stop,
            stop_breach_date=breach_date,
            delayed_exit_date=session if delayed else None,
            loss_beyond_stop=loss_beyond_stop,
        )
    )


def _ownership_delay_report(trades: list[CompletedTrade]) -> dict:
    """Every stop breach that the ownership rules forced to wait, with the cost of waiting."""
    events = [t for t in trades if t.ownership_delayed_exit]
    total = sum((t.loss_beyond_stop or D(0) for t in events), D(0))
    return {
        "count": len(events),
        "total_loss_beyond_stop": str(D(total)),
        "events": [
            {
                "symbol": t.symbol,
                "stop_breach_date": t.stop_breach_date.isoformat() if t.stop_breach_date else None,
                "stop_price": str(t.stop_price),
                "delayed_exit_date": t.delayed_exit_date.isoformat() if t.delayed_exit_date else None,
                "actual_fill": str(t.exit_price),
                "quantity": t.quantity,
                "loss_beyond_stop": str(t.loss_beyond_stop),
            }
            for t in events
        ],
    }


def _check_exit(
    book: SimBook,
    pos: SimPosition,
    feed: _SymbolFeed,
    session: date,
    hold_days: int,
    config: BacktestConfig,
    stats: dict,
    trades: list[CompletedTrade],
) -> None:
    bar = feed.bar_on(session)
    authorised = pos.sell_authorized_date is not None and session >= pos.sell_authorized_date
    held_long_enough = pos.entry_date + timedelta(days=hold_days) <= session

    if not authorised:
        # Ownership safeguard: no sale before authorisation. A stop breach is recorded and executed later.
        if bar is not None and D(bar["low"]) <= pos.stop and not pos.stop_pending:
            pos.stop_pending = True
            pos.stop_breach_date = session
        if pos.stop_pending or held_long_enough:
            stats["ownership_blocked_exits"] += 1
        return

    reason: str | None = None
    px: Decimal | None = None
    open_px = D(bar["open"]) if bar is not None else None
    if pos.stop_pending:
        reason = OWNERSHIP_PENDING_REASON
        px = open_px if open_px is not None else _mark_price(feed, session, pos)
    elif bar is not None:
        high, low = D(bar["high"]), D(bar["low"])
        # Gap checks first (the open is known before any intrabar move), then intrabar.
        # Intrabar rule when both levels are inside one bar: stop first (conservative).
        if open_px <= pos.stop:
            reason, px = "stop", open_px
        elif pos.target is not None and open_px >= pos.target:
            reason, px = "target", open_px
        elif low <= pos.stop:
            reason, px = "stop", pos.stop
        elif pos.target is not None and high >= pos.target:
            reason, px = "target", pos.target

    if reason is None and held_long_enough:
        reason = "time_exit_authorized"
        px = _mark_price(feed, session, pos)

    if reason is not None:
        _close_position(book, pos.symbol, px, reason, session, config, trades)


def _fill_pending(
    book: SimBook,
    pe: dict,
    session: date,
    config: BacktestConfig,
    limits,
    stats: dict,
) -> None:
    """Re-validate a queued entry at its actual fill price. Quantity can only be reduced here."""
    sym = pe["symbol"]
    fill_px: Decimal = pe["fill_price"]
    stop: Decimal = pe["stop"]
    if sym in book.positions or book.open_count() >= config.max_positions or fill_px <= stop:
        stats["fill_rejections"] += 1
        return
    sizing = compute_position_quantity(
        sleeve_equity=pe["equity_ref"],
        risk_per_trade_pct=limits.risk_per_trade_pct,
        entry_price=fill_px,
        stop_price=stop,
        available_cash=book.cash,
        max_position_value=pe["equity_ref"] * limits.max_stock_exposure_pct,
    )
    if sizing.quantity <= 0 or sizing.rejections:
        stats["fill_rejections"] += 1
        return
    qty = min(pe["signal_quantity"], sizing.quantity)
    notional = D(qty) * fill_px
    fees = D(buy_cost(notional, config.cost_scenario)["total"])
    total = notional + fees
    if qty <= 0 or total > book.cash:
        stats["fill_rejections"] += 1
        return
    book.cash = money(book.cash - total)
    book.costs_paid += fees
    book.positions[sym] = SimPosition(
        symbol=sym,
        quantity=qty,
        entry_price=fill_px,
        entry_date=session,
        stop=stop,
        strategy="unified",
        sell_authorized_date=earliest_sell_date(session),
        target=pe["target"],
        signal_quantity=pe["signal_quantity"],
    )


def _queue_entry(
    book: SimBook,
    pending: list[dict],
    feed: _SymbolFeed,
    sym: str,
    sig,
    session: date,
    config: BacktestConfig,
    limits,
    stats: dict,
    equity_ref: Decimal,
) -> None:
    nxt = feed.next_bar(session)
    if nxt is None:
        stats["unfilled_orders"] += 1
        return
    slip = D(config.slippage_bps) / D(10000)
    fill_date = pd.Timestamp(nxt["date"]).date()
    fill_px = (D(nxt["open"]) * (D(1) + slip)).quantize(PRICE_Q)
    assumed = (D(feed.bar_on(session)["close"]) * (D(1) + slip)).quantize(PRICE_Q)
    stop = D(sig.stop_reference) if sig.stop_reference else assumed * D("0.95")
    target = D(sig.target_reference) if sig.target_reference else None
    # Signal-time sizing uses only information known at the signal close (assumed fill, not next open).
    sizing = compute_position_quantity(
        sleeve_equity=equity_ref,
        risk_per_trade_pct=limits.risk_per_trade_pct,
        entry_price=assumed,
        stop_price=stop,
        available_cash=book.cash,
        max_position_value=equity_ref * limits.max_stock_exposure_pct,
    )
    if sizing.quantity <= 0 or sizing.rejections:
        stats["risk_rejections"] += 1
        return
    pending.append(
        {
            "symbol": sym,
            "entry_date": fill_date,
            "fill_price": fill_px,
            "stop": stop,
            "target": target,
            "signal_quantity": sizing.quantity,
            "equity_ref": equity_ref,
        }
    )


def run_backtest(config: BacktestConfig) -> BacktestRun:
    # Every candidate signal on a session asks for the same as-of breadth; compute it once per run (F-4).
    with breadth_cache_scope():
        return _run_backtest(config)


def _run_backtest(config: BacktestConfig) -> BacktestRun:
    config.validate_dates()
    uni_snap, tradable = universe_for_backtest(config.start_date, config.end_date, config.symbols)
    warnings: list[str] = []
    if uni_snap.survivorship_warning:
        warnings.append("Survivorship bias: backtest uses current universe membership for all historical dates.")

    # Registered benchmarks were already partitioned out by the universe provider; they are never scanned.
    benchmark_excluded = list(uni_snap.benchmark_excluded)

    feeds: dict[str, _SymbolFeed] = {}
    for sym in tradable:
        feed = _load_feed(sym, config.end_date)
        if feed is not None:
            feeds[sym] = feed

    sessions = sorted({d for f in feeds.values() for d in f.dates if config.start_date <= d <= config.end_date})
    coverage: dict = {
        "requested_start": config.start_date.isoformat(),
        "requested_end": config.end_date.isoformat(),
        "benchmark_excluded": benchmark_excluded,
        "benchmarks_registered": sorted(benchmark_symbols()),
        "symbols": {},
        "excluded": [],
        "scanned_symbols": [],
        "first_session": None,
        "last_session": None,
        "start_gap_days": None,
        "end_gap_days": None,
    }
    if not sessions:
        coverage["excluded"] = list(tradable)
        warnings.append("No trading sessions with data in requested range")
        return BacktestRun(status=BacktestStatus.FAILED, config=config, warnings=warnings, validation={"coverage": coverage})

    first_s, last_s = sessions[0], sessions[-1]
    for sym in tradable:
        feed = feeds.get(sym)
        in_range = [d for d in feed.dates if config.start_date <= d <= config.end_date] if feed else []
        if not in_range:
            status = "none"
        elif in_range[0] == first_s and in_range[-1] == last_s:
            status = "full"
        else:
            status = "partial"
        first_bar = in_range[0].isoformat() if in_range else None
        last_bar = in_range[-1].isoformat() if in_range else None
        coverage["symbols"][sym] = {"status": status, "first_bar": first_bar, "last_bar": last_bar}
        if status == "none":
            coverage["excluded"].append(sym)
            warnings.append(
                f"Excluded {sym}: no bars in requested range {config.start_date.isoformat()}..{config.end_date.isoformat()}."
            )
        else:
            coverage["scanned_symbols"].append(sym)
            if status == "partial":
                warnings.append(
                    f"Partial coverage for {sym}: bars {first_bar}..{last_bar} inside requested range; "
                    "it is signalled only where its own history supports point-in-time signals."
                )

    coverage["first_session"] = first_s.isoformat()
    coverage["last_session"] = last_s.isoformat()
    coverage["start_gap_days"] = (first_s - config.start_date).days
    coverage["end_gap_days"] = (config.end_date - last_s).days
    if coverage["start_gap_days"] > COVERAGE_GAP_DAYS:
        warnings.append(
            f"Data coverage: first available session {first_s.isoformat()} is "
            f"{coverage['start_gap_days']} days after requested start {config.start_date.isoformat()}."
        )
    if coverage["end_gap_days"] > COVERAGE_GAP_DAYS:
        warnings.append(
            f"Data coverage: last available session {last_s.isoformat()} is "
            f"{coverage['end_gap_days']} days before requested end {config.end_date.isoformat()}; "
            "the run ends at the last available session."
        )

    scanned = coverage["scanned_symbols"]
    prov, grade = _provenance({s: feeds[s] for s in scanned})
    if prov.kind != "imported":
        warnings.append(
            "Synthetic or unknown-provenance data: results are software-regression output, not performance evidence."
        )

    limits = DEFAULT_RISK_CONFIG.swing if config.horizon == "swing" else DEFAULT_RISK_CONFIG.positional
    hold_days = config.hold_days if config.hold_days is not None else (10 if config.horizon == "swing" else 60)
    book = SimBook(cash=D(config.initial_capital))
    curve: list[EquityPoint] = []
    trades: list[CompletedTrade] = []
    stats = {
        "shariah_rejections": 0,
        "risk_rejections": 0,
        "ownership_blocked_exits": 0,
        "unfilled_orders": 0,
        "fill_rejections": 0,
        "stale_marks": 0,
        "max_stale_days": 0,
    }
    stale_over_limit: set[str] = set()
    peak = D(config.initial_capital)
    equity_ref = D(config.initial_capital)
    pending: list[dict] = []

    for session in sessions:
        # 1. Fills.
        for pe in [p for p in pending if p["entry_date"] <= session]:
            pending.remove(pe)
            _fill_pending(book, pe, session, config, limits, stats)

        # 2. Exits.
        for sym, pos in list(book.positions.items()):
            _check_exit(book, pos, feeds[sym], session, hold_days, config, stats, trades)

        # 3. Marks (stale-aware) and session equity point.
        marks: dict[str, Decimal] = {}
        for sym, pos in book.positions.items():
            row, last_d = feeds[sym].last_known(session)
            if row is None:
                marks[sym] = pos.entry_price
                continue
            marks[sym] = D(row["close"])
            if last_d < session:
                gap = int(np.busday_count(np.datetime64(last_d), np.datetime64(session)))
                stats["stale_marks"] += 1
                stats["max_stale_days"] = max(stats["max_stale_days"], gap)
                if gap > STALE_LIMIT_SESSIONS:
                    stale_over_limit.add(sym)
        eq = book.equity(marks)
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else D(0)
        curve.append(EquityPoint(date=session, equity=eq, cash=book.cash, invested=eq - book.cash, drawdown=dd))
        equity_ref = eq

        # 4. Signals over the full tradable universe; queue the top candidate for next-session fill.
        if book.open_count() >= config.max_positions:
            continue
        candidates: list[tuple[float, str, object]] = []
        for sym in scanned:
            feed = feeds[sym]
            if feed.bar_on(session) is None:
                continue  # no bar today: do not generate a signal on stale data
            if sym in book.positions or any(p["symbol"] == sym for p in pending):
                continue
            window = feed.window(session, SIGNAL_LOOKBACK_BARS)
            if window is None or len(window) < MIN_SIGNAL_BARS:
                continue
            sig = generate_unified_signal(sym, window, config.horizon, as_of_index=-1)
            if sig.category not in (SignalCategory.BUY, SignalCategory.STRONG_BUY):
                continue
            if sig.overall_score < config.min_signal_score:
                continue
            ok, _ = check_entry(sym, session, config.shariah_mode)
            if not ok:
                stats["shariah_rejections"] += 1
                continue
            candidates.append((sig.overall_score, sym, sig))
        candidates.sort(key=lambda c: (-c[0], c[1]))
        if candidates:
            _, sym, sig = candidates[0]
            _queue_entry(book, pending, feeds[sym], sym, sig, session, config, limits, stats, equity_ref)

    stats["unfilled_orders"] += len(pending)  # fills dated after the last session never execute

    warnings_stale = stats["stale_marks"]
    if warnings_stale:
        warnings.append(
            f"Stale marks: {warnings_stale} position-session marks used the last known close "
            f"(max gap {stats['max_stale_days']} sessions)."
        )
    if stale_over_limit:
        warnings.append(
            f"Stale marks exceed the {STALE_LIMIT_SESSIONS}-session limit for: {', '.join(sorted(stale_over_limit))}."
        )

    metrics = compute_metrics(curve, trades, D(config.initial_capital), benchmark_return=None, stats=stats)
    run = BacktestRun(
        status=BacktestStatus.COMPLETED,
        config=config,
        warnings=warnings,
        metrics=metrics,
        equity_curve=curve,
        trades=trades,
        evidence_grade=grade,
        data_provenance=prov,
    )
    delay_report = _ownership_delay_report(trades)
    if delay_report["count"]:
        run.warnings.append(
            f"Ownership-delayed stop exits: {delay_report['count']} stop breach(es) occurred while the sale was "
            "not yet authorised and were executed at the first authorised open; "
            f"total loss beyond stop {delay_report['total_loss_beyond_stop']} (before costs)."
        )
    run.validation = build_validation_report(run)
    run.validation["ownership_delayed_stops"] = delay_report
    run.validation["coverage"] = coverage
    run.validation["data_provenance"] = prov.model_dump(mode="json")
    return run
