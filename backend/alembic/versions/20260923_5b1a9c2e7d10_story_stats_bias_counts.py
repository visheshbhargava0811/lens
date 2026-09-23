"""story_stats: stance_counts -> bias_counts (outlet Left/Center/Right, ADR-0020)

Revision ID: 5b1a9c2e7d10
Revises: c07ac0c54704
Create Date: 2026-09-23 02:20:00

"""
from typing import Sequence, Union

from alembic import op


revision: str = "5b1a9c2e7d10"
down_revision: Union[str, Sequence[str], None] = "c07ac0c54704"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("story_stats", "stance_counts", new_column_name="bias_counts")
    # Old rows hold stance buckets; they are recomputed by `make stats`.
    op.execute("DELETE FROM story_stats")


def downgrade() -> None:
    op.alter_column("story_stats", "bias_counts", new_column_name="stance_counts")
    op.execute("DELETE FROM story_stats")
