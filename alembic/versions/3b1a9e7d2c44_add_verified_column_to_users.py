"""add verified column to users

Revision ID: 3b1a9e7d2c44
Revises: 84b4b81f6aa8
Create Date: 2026-03-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3b1a9e7d2c44"
down_revision: Union[str, Sequence[str], None] = "84b4b81f6aa8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("users", "verified", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "verified")
