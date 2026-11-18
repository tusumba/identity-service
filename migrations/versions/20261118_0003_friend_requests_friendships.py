"""friend_requests и friendships

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "identity"


def upgrade() -> None:
    op.create_table(
        "friend_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("from_user_id", sa.Uuid(), nullable=False),
        sa.Column("to_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "accepted", "declined", name="friend_request_status", schema=SCHEMA),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("from_user_id <> to_user_id", name=op.f("ck_friend_requests_not_self")),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("fk_friend_requests_from_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_user_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("fk_friend_requests_to_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_friend_requests")),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_friend_requests_pending_pair",
        "friend_requests",
        [sa.text("least(from_user_id, to_user_id)"), sa.text("greatest(from_user_id, to_user_id)")],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_friend_requests_to_user_id_created_at",
        "friend_requests",
        ["to_user_id", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_friend_requests_from_user_id_created_at",
        "friend_requests",
        ["from_user_id", "created_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "friendships",
        sa.Column("user_low_id", sa.Uuid(), nullable=False),
        sa.Column("user_high_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("user_low_id < user_high_id", name=op.f("ck_friendships_ordered_pair")),
        sa.ForeignKeyConstraint(
            ["user_low_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("fk_friendships_user_low_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_high_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("fk_friendships_user_high_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_low_id", "user_high_id", name=op.f("pk_friendships")),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_friendships_user_high_id"), "friendships", ["user_high_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_table("friendships", schema=SCHEMA)
    op.drop_table("friend_requests", schema=SCHEMA)
    op.execute(f"DROP TYPE {SCHEMA}.friend_request_status")
