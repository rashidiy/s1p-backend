"""Extend telegram_bot_configs for V2: topics, setup, i18n, recordings, digest

Revision ID: extend_telegram_config_v2
Revises: add_is_shadow_to_users
Create Date: 2026-03-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'extend_telegram_config_v2'
down_revision: Union[str, None] = 'add_is_shadow_to_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Supergroup + topics
    op.add_column('telegram_bot_configs', sa.Column('group_chat_id', sa.BigInteger(), nullable=True))
    op.add_column('telegram_bot_configs', sa.Column('topic_ids', JSONB(), nullable=True))
    op.add_column('telegram_bot_configs', sa.Column('invite_link', sa.String(255), nullable=True))
    op.add_column('telegram_bot_configs', sa.Column('setup_status', sa.String(20), server_default=sa.text("'not_started'"), nullable=False))
    op.add_column('telegram_bot_configs', sa.Column('setup_error', sa.Text(), nullable=True))
    op.add_column('telegram_bot_configs', sa.Column('group_name', sa.String(255), nullable=True))

    # Notification settings
    op.add_column('telegram_bot_configs', sa.Column('language', sa.String(10), server_default=sa.text("'ru'"), nullable=False))
    op.add_column('telegram_bot_configs', sa.Column('send_recordings', sa.Boolean(), server_default=sa.text("'true'"), nullable=False))
    op.add_column('telegram_bot_configs', sa.Column('daily_digest', sa.Boolean(), server_default=sa.text("'true'"), nullable=False))
    op.add_column('telegram_bot_configs', sa.Column('dm_notifications', sa.Boolean(), server_default=sa.text("'false'"), nullable=False))
    op.add_column('telegram_bot_configs', sa.Column('digest_message_id', sa.Integer(), nullable=True))

    # Make chat_id nullable (V2 uses group_chat_id instead)
    op.alter_column('telegram_bot_configs', 'chat_id', existing_type=sa.String(100), nullable=True)


def downgrade() -> None:
    op.alter_column('telegram_bot_configs', 'chat_id', existing_type=sa.String(100), nullable=False)

    op.drop_column('telegram_bot_configs', 'digest_message_id')
    op.drop_column('telegram_bot_configs', 'dm_notifications')
    op.drop_column('telegram_bot_configs', 'daily_digest')
    op.drop_column('telegram_bot_configs', 'send_recordings')
    op.drop_column('telegram_bot_configs', 'language')
    op.drop_column('telegram_bot_configs', 'group_name')
    op.drop_column('telegram_bot_configs', 'setup_error')
    op.drop_column('telegram_bot_configs', 'setup_status')
    op.drop_column('telegram_bot_configs', 'invite_link')
    op.drop_column('telegram_bot_configs', 'topic_ids')
    op.drop_column('telegram_bot_configs', 'group_chat_id')
