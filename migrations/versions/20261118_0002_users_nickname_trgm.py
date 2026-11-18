"""триграммный индекс по нику для поиска пользователей

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "identity"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_index(
        "ix_users_nickname_lower_trgm",
        "users",
        [sa.text("lower(nickname) gin_trgm_ops")],
        postgresql_using="gin",
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Расширение не удаляем: база может быть общей, и pg_trgm могли включить до нас.
    op.drop_index("ix_users_nickname_lower_trgm", table_name="users", schema=SCHEMA)
