"""story analysis storage: summary framing/state/source_count/schema_version, claim prompt_version (ADR-0022)

Revision ID: 7c2e4d9a1b36
Revises: 5b1a9c2e7d10
Create Date: 2026-09-23 04:30:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "7c2e4d9a1b36"
down_revision: Union[str, Sequence[str], None] = "5b1a9c2e7d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("story_summaries", sa.Column("framing", JSONB(), nullable=True))
    # published: shown in the UI | review: held for a person (G-OUT-07) | failed: guards never passed
    op.add_column("story_summaries", sa.Column("state", sa.Text(), server_default="published", nullable=False))
    op.add_column("story_summaries", sa.Column("source_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("story_summaries", sa.Column("schema_version", sa.Text(), server_default="1.0", nullable=False))
    op.create_index("ix_story_summaries_story_state", "story_summaries", ["story_id", "state", sa.text("version DESC")])
    op.add_column("claims", sa.Column("prompt_version", sa.Text(), nullable=True))
    op.create_index("ix_claims_article_id", "claims", ["article_id"])


def downgrade() -> None:
    op.drop_index("ix_claims_article_id", table_name="claims")
    op.drop_column("claims", "prompt_version")
    op.drop_index("ix_story_summaries_story_state", table_name="story_summaries")
    for c in ("schema_version", "source_count", "state", "framing"):
        op.drop_column("story_summaries", c)
