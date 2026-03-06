"""add telegram_configs table

Revision ID: add_telegram_configs
Revises: 848cafadb806
Create Date: 2026-03-06 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_telegram_configs'
down_revision: Union[str, None] = '848cafadb806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create telegram_configs table."""
    op.create_table(
        'telegram_configs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=True),
        sa.Column('bot_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_completed_calls', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_missed_calls', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_new_leads', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('notify_deal_stage_change', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', name='uq_telegram_config_company'),
    )
    op.create_index('idx_telegram_configs_company_id', 'telegram_configs', ['company_id'])


def downgrade() -> None:
    """Drop telegram_configs table."""
    op.drop_index('idx_telegram_configs_company_id', table_name='telegram_configs')
    op.drop_table('telegram_configs')
