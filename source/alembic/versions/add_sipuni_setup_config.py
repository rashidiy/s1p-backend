"""add sipuni_setup_configs table

Revision ID: add_sipuni_setup_config
Revises: add_telegram_dm_prefs
Create Date: 2026-03-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'add_sipuni_setup_config'
down_revision: Union[str, None] = 'add_telegram_dm_prefs'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sipuni_setup_configs table."""
    op.create_table(
        'sipuni_setup_configs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('setup_status', sa.String(20), server_default=sa.text("'not_started'"), nullable=False),
        sa.Column('setup_error', sa.Text(), nullable=True),
        sa.Column('setup_method', sa.String(20), nullable=True),
        sa.Column('services_enabled', postgresql.JSONB(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', name='uq_sipuni_setup_config_company'),
    )
    op.create_index('idx_sipuni_setup_configs_company_id', 'sipuni_setup_configs', ['company_id'])


def downgrade() -> None:
    """Drop sipuni_setup_configs table."""
    op.drop_index('idx_sipuni_setup_configs_company_id', table_name='sipuni_setup_configs')
    op.drop_table('sipuni_setup_configs')
