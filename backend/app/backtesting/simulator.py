"""Event-driven historical simulator."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.backtesting.compliance import check_entry
from app.backtesting.costs import buy_cost, sell_cost
from app.backtesting.data import index_as_of, slice_as_of, trading_dates
from app.backtesting.execution import earliest_sell_date, exit_signal_price, fill_market_next_session
from app.backtesting.metrics import compute_metrics
from app.backtesting.portfolio import SimBook, SimPosition
from app.backtesting.schemas import (
    BacktestConfig,
    BacktestMetrics,
    BacktestRun,
    BacktestStatus,
    CompletedTrade,
    EquityPoint,
)
from app.backtesting.universe import symbols_with_data, universe_for_backtest
from app.backtesting.validation import build_validation_report
from app.market_data.repository import get_history_dataframe
from app.portfolio.money import D, money
from app.portfolio.position_sizing import compute_position_quantity
from app.risk.limits import DEFAULT_RISK_CONFIG
from app.signals.generator import generate_unified_signal
from app.signals.schemas import SignalCategory


def _marks(symbols: list[str], as_of: date) -> dict[str, Decimal]:
    marks: dict[str, Decimal] = {}
    for sym in symbols:
        try:
            df = get_history_dataframe(sym, limit=520)
            sub = slice_as_of(df, as_of)
            if not sub.empty:
                marks[sym] = D(sub.iloc[-1]["close"])
        except Exception:
            continue
    return marks


def run_backtest(config: BacktestConfig) -> BacktestRun:
    config.validate_dates()
    uni_snap, syms = universe_for_backtest(config.start_date, config.end_date, config.symbols)
    syms = symbols_with_data(syms, config.start_date, config.end_date)
    warnings = []
    if uni_snap.survivorship_warning:
        warnings.append("Survivorship bias: using current demo universe for all historical dates.")
    if len(syms) < 1:
        return BacktestRun(
            status=BacktestStatus.FAILED,
            config=config,
            warnings=warnings + ["No symbols with data in range"],
        )

    book = SimBook(cash=D(config.initial_capital))
    curve: list[EquityPoint] = []
    trades: list[CompletedTrade] = []
    stats = {"shariah_rejections": 0, "risk_rejections": 0, "ownership_blocked_exits": 0, "unfilled_orders": 0}
    peak = D(config.initial_capital)
    horizon = config.horizon
    limits = DEFAULT_RISK_CONFIG.swing if horizon == "swing" else DEFAULT_RISK_CONFIG.positional
    hold_days = config.hold_days if config.hold_days is not None else (10 if horizon == "swing" else 60)
    pending_entries: list[dict] = []

    for session in trading_dates(syms, config.start_date, config.end_date):
        for pe in [p for p in pending_entries if p["entry_date"] == session]:
            pending_entries.remove(pe)
            sym = pe["symbol"]
            if sym in book.positions:
                continue
            notional = pe["notional"]
            bc = buy_cost(notional, config.cost_scenario)
            fees = D(bc["total"])
            total = notional + fees
            if total > book.cash:
                stats["risk_rejections"] += 1
                continue
            book.cash = money(book.cash - total)
            book.costs_paid += fees
            book.positions[sym] = SimPosition(
                symbol=sym,
                quantity=pe["quantity"],
                entry_price=pe["entry_price"],
                entry_date=session,
                stop=pe["stop"],
                strategy="unified",
                sell_authorized_date=earliest_sell_date(session),
            )
        marks = _marks(syms, session)
        eq = book.equity(marks)
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else D(0)
        curve.append(EquityPoint(date=session, equity=eq, cash=book.cash, invested=eq - book.cash, drawdown=dd))

        # Exits (holding period met; requires sell authorization date in sim)
        for sym, pos in list(book.positions.items()):
            if pos.entry_date + timedelta(days=hold_days) > session:
                continue
            auth_date = pos.sell_authorized_date
            if not auth_date or session < auth_date:
                stats["ownership_blocked_exits"] += 1
                continue
            px = marks.get(sym) or pos.entry_price
            notional = D(pos.quantity) * px
            sc = sell_cost(notional, config.cost_scenario)
            fees = D(sc["total"])
            book.cash = money(book.cash + notional - fees)
            book.costs_paid += fees
            net = notional - D(pos.quantity) * pos.entry_price - fees
            book.realized_pnl += net
            trades.append(
                CompletedTrade(
                    symbol=sym,
                    strategy=pos.strategy,
                    horizon=horizon,
                    entry_date=pos.entry_date,
                    entry_price=pos.entry_price,
                    quantity=pos.quantity,
                    exit_date=session,
                    exit_price=px,
                    gross_pnl=notional - D(pos.quantity) * pos.entry_price,
                    net_pnl=net,
                    costs=fees,
                    holding_days=(session - pos.entry_date).days,
                    exit_reason="time_exit_authorized",
                )
            )
            del book.positions[sym]

        if book.open_count() >= config.max_positions:
            continue

        # Entries — scan symbols by unified signal score
        candidates = []
        for sym in syms[:4]:
            try:
                df = get_history_dataframe(sym, limit=520)
            except Exception:
                continue
            idx = index_as_of(df, session)
            if idx < 60:
                continue
            sub = df.iloc[: idx + 1]
            sig = generate_unified_signal(sym, sub, horizon, as_of_index=-1)
            if sig.category not in (SignalCategory.BUY, SignalCategory.STRONG_BUY):
                continue
            if sig.overall_score < config.min_signal_score:
                continue
            ok, _ = check_entry(sym, session, config.shariah_mode)
            if not ok:
                stats["shariah_rejections"] += 1
                continue
            candidates.append((sig.overall_score, sym, sig))
        candidates.sort(reverse=True)

        for _, sym, sig in candidates[:1]:
            if sym in book.positions:
                continue
            fill = fill_market_next_session(sym, session, config.slippage_bps)
            if not fill:
                stats["unfilled_orders"] += 1
                continue
            entry_px, entry_date = fill
            if entry_date <= session:
                stats["unfilled_orders"] += 1
                continue
            stop = D(sig.stop_reference) if sig.stop_reference else entry_px * D("0.95")
            sizing = compute_position_quantity(
                sleeve_equity=book.equity(marks),
                risk_per_trade_pct=limits.risk_per_trade_pct,
                entry_price=entry_px,
                stop_price=stop,
                available_cash=book.cash,
                max_position_value=book.equity(marks) * limits.max_stock_exposure_pct,
            )
            if sizing.quantity <= 0 or sizing.rejections:
                stats["risk_rejections"] += 1
                continue
            pending_entries.append(
                {
                    "symbol": sym,
                    "entry_date": entry_date,
                    "entry_price": entry_px,
                    "quantity": sizing.quantity,
                    "notional": sizing.notional,
                    "stop": stop,
                }
            )
            break

    final_marks = _marks(syms, config.end_date)
    metrics = compute_metrics(curve, trades, D(config.initial_capital), benchmark_return=None, stats=stats)
    run = BacktestRun(
        status=BacktestStatus.COMPLETED,
        config=config,
        warnings=warnings,
        metrics=metrics,
        equity_curve=curve,
        trades=trades,
    )
    run.validation = build_validation_report(run)
    return run