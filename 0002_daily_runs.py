"""Persist daily collection and channel delivery state across restarts."""
from alembic import op
import sqlalchemy as sa

revision = "0002_daily_runs"
down_revision = "0001_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "daily_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_key", sa.String(160), nullable=False, unique=True),
        sa.Column("day", sa.String(10), nullable=False),
        sa.Column("destination", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_report", sa.JSON(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("daily_runs")
