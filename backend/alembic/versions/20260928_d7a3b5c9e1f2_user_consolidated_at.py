"""memory consolidation marker (Phase 9, docs/11)

Revision ID: d7a3b5c9e1f2
Revises: c4e2a8f1d6b9
Create Date: 2026-09-28 10:30:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7a3b5c9e1f2"
down_revision: Union[str, Sequence[str], None] = "c4e2a8f1d6b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("consolidated_at", sa.TIMESTAMP(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "consolidated_at")
