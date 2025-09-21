"""empty message

Revision ID: c49ccf52318b
Revises: cf5676f5cdff
Create Date: 2025-09-20 23:38:10.741320

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c49ccf52318b'
down_revision: Union[str, Sequence[str], None] = 'cf5676f5cdff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
