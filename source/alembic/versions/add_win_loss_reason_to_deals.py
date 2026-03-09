"""add win_reason and loss_reason to deals

Revision ID: add_win_loss_reason
Revises: 86e897b0e86c
Create Date: 2026-03-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'add_win_loss_reason'
down_revision: Union[str, None] = '86e897b0e86c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('deals', sa.Column('win_reason', sa.String(), nullable=True))
    op.add_column('deals', sa.Column('loss_reason', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('deals', 'loss_reason')
    op.drop_column('deals', 'win_reason')
