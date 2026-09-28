"""anonymous session token for consented users (Phase 9, ADR-0041)

Revision ID: c4e2a8f1d6b9
Revises: b3f1c9e2a7d4
Create Date: 2026-09-28 10:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e2a8f1d6b9"
down_revision: Union[str, Sequence[str], None] = "b3f1c9e2a7d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Only a hash of the random cookie token is stored; deleting the user ends the session.
    op.add_column("users", sa.Column("session_token_hash", sa.Text(), nullable=True))
    op.create_index("ux_users_session_token_hash", "users", ["session_token_hash"], unique=True)
    op.create_index("ix_story_views_user_story", "story_views", ["user_id", "story_id", sa.text("viewed_at DESC")])
    op.create_index("ix_story_views_viewed_at", "story_views", ["viewed_at"])  # retention purge


def downgrade() -> None:
    op.drop_index("ix_story_views_viewed_at", table_name="story_views")
    op.drop_index("ix_story_views_user_story", table_name="story_views")
    op.drop_index("ux_users_session_token_hash", table_name="users")
    op.drop_column("users", "session_token_hash")
