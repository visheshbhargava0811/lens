"""fact-check match audit columns and claim check marker (Phase 8, ADR-0040)

Revision ID: b3f1c9e2a7d4
Revises: 9d4f1a7c3e52
Create Date: 2026-09-27 16:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3f1c9e2a7d4"
down_revision: Union[str, Sequence[str], None] = "9d4f1a7c3e52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The verifier's reasoning and versions are kept with each stored match (rule 3, rule 7).
    op.add_column("claim_fact_check_matches", sa.Column("rationale", sa.Text(), nullable=True))
    op.add_column("claim_fact_check_matches", sa.Column("schema_version", sa.Text(), nullable=True))
    op.add_column("claim_fact_check_matches", sa.Column("prompt_version", sa.Text(), nullable=True))
    # A claim with no match stores no row, so this marks it as checked (no re-verification every pass).
    op.add_column("claims", sa.Column("factcheck_checked_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("claims", "factcheck_checked_at")
    for c in ("prompt_version", "schema_version", "rationale"):
        op.drop_column("claim_fact_check_matches", c)
