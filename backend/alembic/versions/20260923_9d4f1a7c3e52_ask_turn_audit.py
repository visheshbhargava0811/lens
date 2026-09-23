"""ask_turns audit columns (G-OPS-04, ADR-0033)

Revision ID: 9d4f1a7c3e52
Revises: 7c2e4d9a1b36
Create Date: 2026-09-23 16:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision: str = "9d4f1a7c3e52"
down_revision: Union[str, Sequence[str], None] = "7c2e4d9a1b36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ask_turns", sa.Column("outcome", sa.Text(), nullable=True))
    op.add_column("ask_turns", sa.Column("abstain_reason", sa.Text(), nullable=True))
    op.add_column("ask_turns", sa.Column("evidence_article_ids", ARRAY(sa.Text()), nullable=True))
    op.add_column("ask_turns", sa.Column("verifier", JSONB(), nullable=True))
    op.add_column("ask_turns", sa.Column("errors", JSONB(), nullable=True))
    op.add_column("ask_turns", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.create_index("ix_ask_turns_created_at", "ask_turns", ["created_at"])  # retention purge


def downgrade() -> None:
    op.drop_index("ix_ask_turns_created_at", table_name="ask_turns")
    for c in ("latency_ms", "errors", "verifier", "evidence_article_ids", "abstain_reason", "outcome"):
        op.drop_column("ask_turns", c)
