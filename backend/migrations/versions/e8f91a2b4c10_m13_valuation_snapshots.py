"""m13_valuation_snapshots

Revision ID: e8f91a2b4c10
Revises: c4d2e8a91f03
Create Date: 2026-11-24 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f91a2b4c10"
down_revision: Union[str, None] = "c4d2e8a91f03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "portfolio_valuation_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("book_name", sa.String(length=64), nullable=False),
        sa.Column("portfolio_book_id", sa.Integer(), nullable=True),
        sa.Column("valued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.Column("trigger", sa.String(length=24), nullable=False),
        sa.Column("portfolio_equity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("available_cash", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("reserved_cash", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("invested_market_value", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("total_pnl", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("swing_equity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("positional_equity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("cash_reserve", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("equity_peak_prior", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("equity_peak_at_snapshot", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("drawdown_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("drawdown_pct", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("price_quality_json", sa.JSON(), nullable=False),
        sa.Column("valuation_complete", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_book_id"], ["portfolio_books.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_portfolio_valuation_snapshots_book_name"), "portfolio_valuation_snapshots", ["book_name"])
    op.create_index(op.f("ix_portfolio_valuation_snapshots_valuation_date"), "portfolio_valuation_snapshots", ["valuation_date"])
    op.create_index(op.f("ix_portfolio_valuation_snapshots_trigger"), "portfolio_valuation_snapshots", ["trigger"])
    op.create_index(op.f("ix_portfolio_valuation_snapshots_valued_at"), "portfolio_valuation_snapshots", ["valued_at"])
    op.create_index(
        "uq_valuation_daily",
        "portfolio_valuation_snapshots",
        ["book_name", "valuation_date"],
        unique=True,
        postgresql_where=sa.text("trigger = 'daily'"),
    )


def downgrade() -> None:
    op.drop_index("uq_valuation_daily", table_name="portfolio_valuation_snapshots")
    op.drop_index(op.f("ix_portfolio_valuation_snapshots_valued_at"), table_name="portfolio_valuation_snapshots")
    op.drop_index(op.f("ix_portfolio_valuation_snapshots_trigger"), table_name="portfolio_valuation_snapshots")
    op.drop_index(op.f("ix_portfolio_valuation_snapshots_valuation_date"), table_name="portfolio_valuation_snapshots")
    op.drop_index(op.f("ix_portfolio_valuation_snapshots_book_name"), table_name="portfolio_valuation_snapshots")
    op.drop_table("portfolio_valuation_snapshots")