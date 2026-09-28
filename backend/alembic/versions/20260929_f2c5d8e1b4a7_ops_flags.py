"""kill switch flags (G-OPS-03, ADR-0045)

Revision ID: f2c5d8e1b4a7
Revises: e1b4c7d2a9f3
Create Date: 2026-09-29 10:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "f2c5d8e1b4a7"
down_revision: Union[str, Sequence[str], None] = "e1b4c7d2a9f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ops_flags",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ops_flags")
