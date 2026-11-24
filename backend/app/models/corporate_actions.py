from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CorporateAction(Base):
    """Corporate action metadata — ingest from verified sources only."""

    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="NSE")
    action_type: Mapped[str] = mapped_column(String(32))  # split, bonus, dividend, rights, merger
    effective_date: Mapped[date] = mapped_column(Date, index=True)
    ratio: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    factor: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)