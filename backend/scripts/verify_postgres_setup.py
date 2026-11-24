"""Non-destructive PostgreSQL setup checks (reads root .env via app settings)."""

from __future__ import annotations

import json
import sys

from sqlalchemy import inspect, select, text

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models.portfolio_risk import PortfolioBook
from app.models.shariah_execution import ExecutionStateRow

EXPECTED_TABLES = {
    "alembic_version",
    "ohlcv_candles",
    "stocks",
    "market_data_imports",
    "corporate_actions",
    "portfolio_books",
    "portfolio_valuation_snapshots",
    "execution_state",
    "research_signals",
    "signal_lifecycle_events",
    "risk_configurations",
    "allocation_proposals",
    "rebalance_proposals",
    "risk_events",
    "backtest_runs",
    "shariah_eligibility",
    "shariah_snapshots",
    "paper_portfolios",
    "paper_positions",
    "paper_trades",
    "shariah_screenings",
}

MARKER_BOOK = "_verify_persistence_book"
MARKER_EXEC = "_verify_persistence_exec"


def main() -> int:
    if not settings.database_enabled or engine is None or SessionLocal is None:
        print("FAIL: DATABASE_URL not loaded (check project root .env)")
        return 1

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(f"OK: connected, alembic={rev}")

    names = set(inspect(engine).get_table_names())
    missing = EXPECTED_TABLES - names
    extra = names - EXPECTED_TABLES
    if missing:
        print(f"FAIL: missing tables: {sorted(missing)}")
        return 1
    print(f"OK: {len(names)} tables present")
    if extra:
        print(f"NOTE: extra tables: {sorted(extra)}")

    from app.portfolio import store as portfolio_store
    from app.portfolio.money import D

    def stamp_book(st: portfolio_store.BookState) -> None:
        st.ledger_seq += 1
        from app.portfolio.schemas import CashLedgerEntry, LedgerReason

        st.ledger.append(
            CashLedgerEntry(
                id=st.ledger_seq,
                sleeve="swing",
                reason=LedgerReason.ADJUSTMENT,
                amount=D(0),
                balance_after=st.balances["swing"],
                note=MARKER_BOOK,
            )
        )
        st.state_version += 1

    portfolio_store.update_book(stamp_book)
    with SessionLocal() as session:
        row = session.execute(
            select(PortfolioBook).where(PortfolioBook.name == "default")
        ).scalar_one_or_none()
        if not row or MARKER_BOOK not in json.dumps(row.state_json):
            print("FAIL: portfolio_books row missing marker")
            return 1
    print("OK: portfolio_books persisted")

    from app.execution import store as exec_store

    st = exec_store._load()  # noqa: SLF001
    st["_verify_marker"] = MARKER_EXEC
    exec_store._save(st)  # noqa: SLF001

    with SessionLocal() as session:
        erow = session.execute(
            select(ExecutionStateRow).where(ExecutionStateRow.name == "default")
        ).scalar_one_or_none()
        if not erow or erow.state_json.get("_verify_marker") != MARKER_EXEC:
            print("FAIL: execution_state row missing marker")
            return 1
    print("OK: execution_state persisted")

    # restart simulation: clear in-memory caches, reload from DB
    portfolio_store._BOOK_MEM = None  # noqa: SLF001
    exec_store._STATE = None  # noqa: SLF001
    reloaded = portfolio_store.load_book()
    if not any(getattr(e, "note", None) == MARKER_BOOK for e in reloaded.ledger):
        print("FAIL: portfolio marker lost after reload")
        return 1
    est = exec_store._load()  # noqa: SLF001
    if est.get("_verify_marker") != MARKER_EXEC:
        print("FAIL: execution marker lost after reload")
        return 1
    print("OK: reload after in-process cache clear (restart simulation)")

    cleanup_exec = exec_store._load()  # noqa: SLF001
    cleanup_exec.pop("_verify_marker", None)
    exec_store._save(cleanup_exec)  # noqa: SLF001

    def strip_marker(st: portfolio_store.BookState) -> None:
        st.ledger = [e for e in st.ledger if getattr(e, "note", None) != MARKER_BOOK]

    portfolio_store.update_book(strip_marker)
    print("OK: verification markers removed")
    print("PASS: PostgreSQL integration verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())