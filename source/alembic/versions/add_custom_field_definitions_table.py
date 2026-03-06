"""add custom_field_definitions table

Revision ID: add_custom_field_definitions
Revises: 848cafadb806
Create Date: 2026-03-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_custom_field_definitions'
down_revision: Union[str, None] = '848cafadb806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create custom_field_definitions table."""
    op.create_table(
        'custom_field_definitions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('entity_type', sa.String(length=20), nullable=False),
        sa.Column('field_name', sa.String(length=100), nullable=False),
        sa.Column('field_type', sa.String(length=20), nullable=False),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('required', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'entity_type', 'field_name', name='uq_company_entity_field_name'),
    )
    op.create_index('idx_cfd_company_id', 'custom_field_definitions', ['company_id'], unique=False)
    op.create_index('idx_cfd_company_entity', 'custom_field_definitions', ['company_id', 'entity_type'], unique=False)


def downgrade() -> None:
    """Drop custom_field_definitions table."""
    op.drop_index('idx_cfd_company_entity', table_name='custom_field_definitions')
    op.drop_index('idx_cfd_company_id', table_name='custom_field_definitions')
    op.drop_table('custom_field_definitions')
