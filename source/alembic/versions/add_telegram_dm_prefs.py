"""Add telegram_dm_prefs JSONB to users for DM notification preferences

Revision ID: add_telegram_dm_prefs
Revises: extend_telegram_config_v2
Create Date: 2026-03-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'add_telegram_dm_prefs'
down_revision: Union[str, None] = 'extend_telegram_config_v2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column(
        'telegram_dm_prefs',
        JSONB(),
        nullable=True,
        server_default=sa.text("'{}'::jsonb"),
    ))


def downgrade() -> None:
    op.drop_column('users', 'telegram_dm_prefs')
