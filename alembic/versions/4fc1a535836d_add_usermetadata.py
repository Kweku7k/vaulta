"""add usermetadata

Revision ID: 4fc1a535836d
Revises: ed4b6aa2386d
Create Date: 2025-09-20 17:23:45.303944

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4fc1a535836d'
down_revision: Union[str, Sequence[str], None] = 'ed4b6aa2386d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column('usermetadata', sa.String(255), nullable=True)
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users","usermetadata")

