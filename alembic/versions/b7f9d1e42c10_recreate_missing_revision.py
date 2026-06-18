"""recreate missing revision

Revision ID: b7f9d1e42c10
Revises: beb899f3fba7
Create Date: 2026-06-18 09:36:43.749441

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f9d1e42c10'
down_revision: Union[str, Sequence[str], None] = 'beb899f3fba7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
