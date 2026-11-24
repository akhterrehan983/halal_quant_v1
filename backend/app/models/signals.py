from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResearchSignal(Base):
    __tablename__ = "research_signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    horizon: Mapped[str] = mapped_column(String(16), index=True)
    evaluation_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(24))
    overall_score: Mapped[int] = mapped_column(Integer)
    lifecycle_state: Mapped[str] = mapped_column(String(24), index=True)
    market_regime: Mapped[str] = mapped_column(String(32))
    entry_reference: Mapped[float] = mapped_column(Float)
    stop_reference: Mapped[float] = mapped_column(Float)
    target_reference: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSON)
    expires_after_sessions: Mapped[int] = mapped_column(Integer, default=15)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class SignalLifecycleEvent(Base):
    __tablename__ = "signal_lifecycle_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[int] = mapped_column(Integer, index=True)
    from_state: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_state: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)