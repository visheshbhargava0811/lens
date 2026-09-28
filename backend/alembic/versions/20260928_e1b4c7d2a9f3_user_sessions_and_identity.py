"""sign-in: sessions per device and a hashed OAuth identity (ADR-0044)

Revision ID: e1b4c7d2a9f3
Revises: d7a3b5c9e1f2
Create Date: 2026-09-28 16:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "e1b4c7d2a9f3"
down_revision: Union[str, Sequence[str], None] = "d7a3b5c9e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.Text, primary_key=True),  # SHA-256 of the cookie token; the token is never stored
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.execute(
        "INSERT INTO user_sessions (token_hash, user_id, created_at) "
        "SELECT session_token_hash, id, created_at FROM users WHERE session_token_hash IS NOT NULL"
    )
    op.drop_index("ux_users_session_token_hash", table_name="users")
    op.drop_column("users", "session_token_hash")
    op.add_column("users", sa.Column("identity_provider", sa.Text, nullable=True))
    op.add_column("users", sa.Column("identity_hash", sa.Text, nullable=True))  # SHA-256 of provider:subject
    op.create_index("ux_users_identity_hash", "users", ["identity_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_users_identity_hash", table_name="users")
    op.drop_column("users", "identity_hash")
    op.drop_column("users", "identity_provider")
    op.add_column("users", sa.Column("session_token_hash", sa.Text, nullable=True))
    op.execute(
        "UPDATE users u SET session_token_hash = s.token_hash FROM "
        "(SELECT DISTINCT ON (user_id) user_id, token_hash FROM user_sessions ORDER BY user_id, created_at DESC) s "
        "WHERE s.user_id = u.id"
    )
    op.create_index("ux_users_session_token_hash", "users", ["session_token_hash"], unique=True)
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
