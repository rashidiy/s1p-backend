"""Add is_shadow column to users table

Revision ID: add_is_shadow_to_users
Revises: add_avatar_to_users
Create Date: 2026-03-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'add_is_shadow_to_users'
down_revision: Union[str, None] = 'add_avatar_to_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_shadow', sa.Boolean(), server_default=sa.text("'false'"), nullable=False))
    # Mark existing shadow users
    op.execute("UPDATE users SET is_shadow = true WHERE email LIKE 'owner-shadow-%@s1p.internal'")


def downgrade() -> None:
    op.drop_column('users', 'is_shadow')
