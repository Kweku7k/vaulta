"""add_pep_fields_to_user_kyc

Revision ID: a1b2c3d4e5f6
Revises: 634d9a99058e
Create Date: 2026-05-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '634d9a99058e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_kyc', sa.Column('pep_is_pep', sa.Boolean(), nullable=True))
    op.add_column('user_kyc', sa.Column('pep_affiliation', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_kyc', 'pep_affiliation')
    op.drop_column('user_kyc', 'pep_is_pep')
