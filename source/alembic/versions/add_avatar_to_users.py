"""Add avatar and avatar_is_custom columns to users table

Revision ID: add_avatar_to_users
Revises: add_telegram_auth_overhaul
Create Date: 2026-03-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_avatar_to_users'
down_revision: Union[str, None] = 'add_telegram_auth_overhaul'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('avatar_is_custom', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('users', 'avatar_is_custom')
    op.drop_column('users', 'avatar')
