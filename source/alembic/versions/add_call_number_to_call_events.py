"""add call_number to call_events

Revision ID: add_call_number
Revises: add_permission_groups
Create Date: 2026-02-15

Adds company-scoped call_number column to call_events table.
Backfills existing rows with ROW_NUMBER() partitioned by company_id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_call_number'
down_revision: Union[str, None] = 'add_permission_groups'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column as nullable first
    op.add_column(
        'call_events',
        sa.Column('call_number', sa.Integer(), nullable=True)
    )

    # Backfill existing rows: assign sequential numbers per company
    op.execute("""
        UPDATE call_events
        SET call_number = sub.rn
        FROM (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY company_id ORDER BY created_at
                   ) AS rn
            FROM call_events
        ) sub
        WHERE call_events.id = sub.id
    """)

    # Set NOT NULL after backfill
    op.alter_column('call_events', 'call_number', nullable=False)

    # Add unique constraint and index
    op.create_unique_constraint(
        'uq_company_call_number', 'call_events',
        ['company_id', 'call_number']
    )
    op.create_index(
        'idx_call_events_call_number', 'call_events', ['call_number']
    )


def downgrade() -> None:
    op.drop_index('idx_call_events_call_number', table_name='call_events')
    op.drop_constraint('uq_company_call_number', 'call_events', type_='unique')
    op.drop_column('call_events', 'call_number')
