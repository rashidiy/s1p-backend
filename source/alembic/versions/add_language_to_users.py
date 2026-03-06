"""add language column to users

Revision ID: add_language_to_users
Revises: replace_uuid_with_int_id
Create Date: 2026-03-06

Adds a `language` VARCHAR(5) column to the users table with default 'en'.
Supports per-user locale preference for the i18n system.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_language_to_users'
down_revision: Union[str, None] = 'replace_uuid_with_int_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add language column to users table."""
    op.add_column(
        'users',
        sa.Column('language', sa.String(length=5), server_default='en', nullable=False),
    )


def downgrade() -> None:
    """Remove language column from users table."""
    op.drop_column('users', 'language')
