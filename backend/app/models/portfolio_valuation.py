from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PortfolioValuationSnapshot(Base):
    __tablename__ = "portfolio_valuation_snapshots"
    __table_args__ = (
        Index(
            "uq_valuation_daily",
            "book_name",
            "valuation_date",
            unique=True,
            postgresql_where=text("trigger = 'daily'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    portfolio_book_id: Mapped[int | None] = mapped_column(ForeignKey("portfolio_books.id"), nullable=True)
    valued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    portfolio_equity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    available_cash: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    reserved_cash: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    invested_market_value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    total_pnl: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    swing_equity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    positional_equity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    cash_reserve: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    equity_peak_prior: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    equity_peak_at_snapshot: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    drawdown_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    drawdown_pct: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    price_quality_json: Mapped[dict] = mapped_column(JSON, default=dict)
    valuation_complete: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)