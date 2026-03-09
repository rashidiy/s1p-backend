"""add created_by to leads and deals

Revision ID: add_created_by_to_leads
Revises: add_language_to_users
Create Date: 2026-03-09

Adds created_by UUID column to the leads and deals tables with foreign keys to users.id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_created_by_to_leads'
down_revision: Union[str, None] = 'add_language_to_users'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add created_by column to leads and deals tables."""
    op.add_column(
        'leads',
        sa.Column('created_by', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_leads_created_by_users',
        'leads',
        'users',
        ['created_by'],
        ['id'],
        ondelete='SET NULL',
    )

    op.add_column(
        'deals',
        sa.Column('created_by', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_deals_created_by_users',
        'deals',
        'users',
        ['created_by'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Remove created_by column from leads and deals tables."""
    op.drop_constraint('fk_deals_created_by_users', 'deals', type_='foreignkey')
    op.drop_column('deals', 'created_by')
    op.drop_constraint('fk_leads_created_by_users', 'leads', type_='foreignkey')
    op.drop_column('leads', 'created_by')
