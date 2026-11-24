"""milestone7_backtesting

Revision ID: c4d2e8a91f03
Revises: 38a76ff1fe77
Create Date: 2026-11-20 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d2e8a91f03"
down_revision: Union[str, None] = "38a76ff1fe77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_backtest_runs_name"), "backtest_runs", ["name"], unique=False)
    op.create_index(op.f("ix_backtest_runs_status"), "backtest_runs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_backtest_runs_status"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_name"), table_name="backtest_runs")
    op.drop_table("backtest_runs")