"""users и refresh_tokens

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "identity"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column(
            "global_role",
            sa.Enum("user", "moderator", name="global_role", schema=SCHEMA),
            server_default="user",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True, schema=SCHEMA
    )
    op.create_index(
        "uq_users_nickname_lower", "users", [sa.text("lower(nickname)")], unique=True, schema=SCHEMA
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], schema=SCHEMA)
    op.create_index(
        op.f("ix_refresh_tokens_session_id"), "refresh_tokens", ["session_id"], schema=SCHEMA
    )
    op.create_index(
        op.f("ix_refresh_tokens_expires_at"), "refresh_tokens", ["expires_at"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
    op.execute(f"DROP TYPE {SCHEMA}.global_role")
