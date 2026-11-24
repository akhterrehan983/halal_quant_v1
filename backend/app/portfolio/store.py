"""Portfolio book persistence — PostgreSQL or in-memory demo store."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.config import settings as app_settings
from app.market_data.repository import SymbolNotFoundError, get_history_dataframe, last_close_prices
from app.models.portfolio_risk import (
    AllocationProposalRecord,
    PortfolioBook,
    RebalanceProposalRecord,
    RiskConfigurationRecord,
    RiskEventRecord,
)
from app.portfolio.cash import init_sleeve_balances
from app.portfolio.money import D, money
from app.portfolio.performance import build_summary
from app.portfolio.schemas import (
    AllocationProposal,
    ProposalStatus,
    RebalanceProposal,
    SleeveHolding,
)
from app.risk.schemas import RiskConfiguration, RiskEvent
from app.core.exceptions import ConcurrentBookUpdate

logger = logging.getLogger(__name__)

_BOOK_MEM: dict | None = None
_PROPOSAL_SEQ = 0
_EVENT_SEQ = 0


@dataclass
class BookState:
    total_capital: Decimal
    balances: dict[str, Decimal]
    reserved: dict[str, Decimal] = field(default_factory=lambda: {"swing": D(0), "positional": D(0)})
    holdings_swing: list[SleeveHolding] = field(default_factory=list)
    holdings_positional: list[SleeveHolding] = field(default_factory=list)
    realized_pnl: Decimal = field(default_factory=lambda: D(0))
    peak_value: Decimal = field(default_factory=lambda: D(0))
    drawdown_locked: bool = False
    ledger: list = field(default_factory=list)
    ledger_seq: int = 0
    proposals: list[AllocationProposal] = field(default_factory=list)
    rebalance: list[RebalanceProposal] = field(default_factory=list)
    risk_events: list[RiskEvent] = field(default_factory=list)
    last_valuation_date: date | None = None
    state_version: int = 0

    def holdings_for(self, sleeve: str) -> list[SleeveHolding]:
        return self.holdings_swing if sleeve == "swing" else self.holdings_positional

    def all_holdings(self) -> list[SleeveHolding]:
        return self.holdings_swing + self.holdings_positional

    def to_json(self) -> dict:
        return {
            "total_capital": str(self.total_capital),
            "balances": {k: str(v) for k, v in self.balances.items()},
            "reserved": {k: str(v) for k, v in self.reserved.items()},
            "holdings_swing": [h.model_dump(mode="json") for h in self.holdings_swing],
            "holdings_positional": [h.model_dump(mode="json") for h in self.holdings_positional],
            "realized_pnl": str(self.realized_pnl),
            "peak_value": str(self.peak_value),
            "drawdown_locked": self.drawdown_locked,
            "ledger": [
                e.model_dump(mode="json") if hasattr(e, "model_dump") else e for e in self.ledger
            ],
            "ledger_seq": self.ledger_seq,
            "proposals": [p.model_dump(mode="json") for p in self.proposals],
            "rebalance": [r.model_dump(mode="json") for r in self.rebalance],
            "risk_events": [e.model_dump(mode="json") for e in self.risk_events],
            "last_valuation_date": self.last_valuation_date.isoformat() if self.last_valuation_date else None,
            "state_version": self.state_version,
        }

    @classmethod
    def from_json(cls, data: dict) -> BookState:
        from app.portfolio.schemas import CashLedgerEntry

        return cls(
            total_capital=D(data["total_capital"]),
            balances={k: D(v) for k, v in data["balances"].items()},
            reserved={k: D(v) for k, v in data.get("reserved", {}).items()},
            holdings_swing=[SleeveHolding.model_validate(h) for h in data.get("holdings_swing", [])],
            holdings_positional=[SleeveHolding.model_validate(h) for h in data.get("holdings_positional", [])],
            realized_pnl=D(data.get("realized_pnl", "0")),
            peak_value=D(data.get("peak_value", data.get("total_capital", "0"))),
            drawdown_locked=bool(data.get("drawdown_locked", False)),
            ledger=[CashLedgerEntry.model_validate(e) for e in data.get("ledger", [])],
            ledger_seq=int(data.get("ledger_seq", 0)),
            proposals=[AllocationProposal.model_validate(p) for p in data.get("proposals", [])],
            rebalance=[RebalanceProposal.model_validate(r) for r in data.get("rebalance", [])],
            risk_events=[RiskEvent.model_validate(e) for e in data.get("risk_events", [])],
            last_valuation_date=date.fromisoformat(data["last_valuation_date"])
            if data.get("last_valuation_date")
            else None,
            state_version=int(data.get("state_version", 0)),
        )


def _default_book() -> BookState:
    from app.portfolio.schemas import CashLedgerEntry, LedgerReason

    total = D(app_settings.starting_cash)
    cfg = get_risk_config()
    balances = init_sleeve_balances(total, cfg.swing_capital_pct, cfg.positional_capital_pct, cfg.cash_reserve_pct)
    state = BookState(total_capital=total, balances=balances, peak_value=total)
    for sleeve, bal in balances.items():
        state.ledger_seq += 1
        state.ledger.append(
            CashLedgerEntry(
                id=state.ledger_seq,
                sleeve=sleeve,
                reason=LedgerReason.INITIAL_FUNDING,
                amount=bal,
                balance_after=bal,
                note="Initial sleeve allocation",
            )
        )
    return state


def load_book() -> BookState:
    global _BOOK_MEM
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            rec = session.execute(select(PortfolioBook).where(PortfolioBook.name == "default")).scalar_one_or_none()
            if not rec:
                state = _default_book()
                rec = PortfolioBook(name="default", state_json=state.to_json())
                session.add(rec)
                session.commit()
                return state
            return BookState.from_json(rec.state_json)

    if _BOOK_MEM is None:
        _BOOK_MEM = _default_book().to_json()
    return BookState.from_json(_BOOK_MEM)


def save_book(state: BookState, *, expected_version: int | None = None) -> None:
    global _BOOK_MEM
    payload = state.to_json()
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            rec = session.execute(
                select(PortfolioBook).where(PortfolioBook.name == "default").with_for_update()
            ).scalar_one_or_none()
            if not rec:
                rec = PortfolioBook(name="default", state_json=payload)
                session.add(rec)
            else:
                current_ver = int(rec.state_json.get("state_version", 0))
                if expected_version is not None and current_ver != expected_version:
                    raise ConcurrentBookUpdate()
                rec.state_json = payload
                rec.updated_at = datetime.utcnow()
            session.commit()
            return
    if expected_version is not None and _BOOK_MEM is not None:
        mem_ver = int(_BOOK_MEM.get("state_version", 0))
        if mem_ver != expected_version:
            raise ConcurrentBookUpdate()
    _BOOK_MEM = payload


def update_book(mutator, *, max_retries: int = 5) -> BookState:
    """Atomic read-modify-write with optimistic versioning."""
    last_exc: Exception | None = None
    for _ in range(max_retries):
        state = load_book()
        expected = state.state_version
        mutator(state)
        state.state_version = expected + 1
        try:
            save_book(state, expected_version=expected)
            return state
        except ConcurrentBookUpdate as exc:
            last_exc = exc
            continue
    raise last_exc or ConcurrentBookUpdate()


def _merge_holding(state: BookState, sleeve: str, symbol: str, quantity: int, price: Decimal) -> None:
    sym = symbol.upper()
    holdings = state.holdings_for(sleeve)
    for h in holdings:
        if h.symbol == sym:
            old_qty = h.quantity
            new_qty = old_qty + quantity
            if new_qty <= 0:
                merged = [x for x in holdings if x.symbol != sym]
            else:
                total_cost = D(old_qty) * D(h.average_entry) + D(quantity) * D(price)
                h.quantity = new_qty
                h.average_entry = money(total_cost / new_qty) if new_qty else D(0)
                merged = holdings
            if sleeve == "swing":
                state.holdings_swing = merged
            else:
                state.holdings_positional = merged
            return
    holdings = list(holdings)
    holdings.append(
        SleeveHolding(symbol=sym, sleeve=sleeve, quantity=quantity, average_entry=price, stop_reference=None)
    )
    if sleeve == "swing":
        state.holdings_swing = holdings
    else:
        state.holdings_positional = holdings


def get_risk_config() -> RiskConfiguration:
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            rec = session.execute(select(RiskConfigurationRecord).limit(1)).scalar_one_or_none()
            if rec and rec.config_json:
                return RiskConfiguration.model_validate(rec.config_json)
    return RiskConfiguration()


def save_risk_config(cfg: RiskConfiguration) -> None:
    cfg.validate_allocations()
    data = cfg.model_dump(mode="json")
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            rec = session.execute(select(RiskConfigurationRecord).limit(1)).scalar_one_or_none()
            if not rec:
                rec = RiskConfigurationRecord(config_json=data)
                session.add(rec)
            else:
                rec.config_json = data
            session.commit()
            return


def mark_prices() -> dict[str, Decimal]:
    raw = last_close_prices()
    return {k.upper(): D(v) for k, v in raw.items()}


def get_history(symbol: str):
    try:
        return get_history_dataframe(symbol, limit=120)
    except SymbolNotFoundError:
        return None


def read_summary(state: BookState, prices: dict[str, Decimal]):
    cfg = get_risk_config()
    return build_summary(
        total_capital=state.total_capital,
        balances=state.balances,
        reserved=state.reserved,
        holdings_swing=state.holdings_swing,
        holdings_pos=state.holdings_positional,
        prices=prices,
        realized_pnl=state.realized_pnl,
        peak_value=state.peak_value,
        drawdown_locked=state.drawdown_locked,
        swing_alloc=cfg.swing_capital_pct,
        pos_alloc=cfg.positional_capital_pct,
    )


def persist_valuation(state: BookState, prices: dict[str, Decimal]):
    summary = read_summary(state, prices)
    if summary.portfolio_value > state.peak_value:
        state.peak_value = summary.portfolio_value
    state.last_valuation_date = date.today()
    save_book(state)
    return summary


def build_summary_from_state(state: BookState, prices: dict[str, Decimal], *, persist: bool = True):
    if persist:
        return persist_valuation(state, prices)
    return read_summary(state, prices)


def record_risk_event(state: BookState, event_type: str, message: str, detail: dict) -> RiskEvent:
    global _EVENT_SEQ
    _EVENT_SEQ += 1
    ev = RiskEvent(event_id=_EVENT_SEQ, event_type=event_type, message=message, detail=detail, created_at=datetime.utcnow())
    state.risk_events.append(ev)
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            session.add(RiskEventRecord(event_type=event_type, message=message, detail_json=detail))
            session.commit()
    save_book(state)
    return ev


def persist_proposal(proposal: AllocationProposal) -> AllocationProposal:
    global _PROPOSAL_SEQ
    state = load_book()
    for p in state.proposals:
        if (
            p.status == ProposalStatus.PENDING
            and p.symbol == proposal.symbol
            and p.sleeve == proposal.sleeve
            and p.signal_id == proposal.signal_id
        ):
            return p
    _PROPOSAL_SEQ += 1
    proposal.proposal_id = _PROPOSAL_SEQ
    proposal.created_at = datetime.utcnow()
    state.proposals.insert(0, proposal)
    save_book(state)
    if settings.database_enabled and SessionLocal:
        with SessionLocal() as session:
            session.add(
                AllocationProposalRecord(
                    proposal_id=proposal.proposal_id,
                    symbol=proposal.symbol,
                    sleeve=proposal.sleeve,
                    status=proposal.status.value,
                    payload_json=proposal.model_dump(mode="json"),
                )
            )
            session.commit()
    return proposal


def list_proposals(status: str | None = None) -> list[AllocationProposal]:
    state = load_book()
    if status:
        return [p for p in state.proposals if p.status.value == status]
    return list(state.proposals)


def get_proposal(proposal_id: int) -> AllocationProposal | None:
    for p in list_proposals():
        if p.proposal_id == proposal_id:
            return p
    return None