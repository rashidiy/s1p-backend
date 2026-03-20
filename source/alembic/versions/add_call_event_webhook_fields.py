"""add webhook event fields to call_events

Revision ID: add_call_event_webhook_fields
Revises: add_sipuni_setup_config
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'add_call_event_webhook_fields'
down_revision: Union[str, None] = 'add_sipuni_setup_config'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add call_answer_timestamp, scheme/transfer fields, and RINGING status."""
    # Add RINGING to call_status_enum
    op.execute("ALTER TYPE call_status_enum ADD VALUE IF NOT EXISTS 'RINGING' BEFORE 'ANSWER'")

    # Add new columns
    op.add_column('call_events', sa.Column('call_answer_timestamp', sa.BigInteger(), nullable=True))
    op.add_column('call_events', sa.Column('scheme_name', sa.String(255), nullable=True))
    op.add_column('call_events', sa.Column('scheme_number', sa.String(100), nullable=True))
    op.add_column('call_events', sa.Column('transfer_from', sa.String(50), nullable=True))
    op.add_column('call_events', sa.Column('last_called', sa.String(50), nullable=True))
    op.add_column('call_events', sa.Column('is_transfer', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    """Remove webhook event fields."""
    op.drop_column('call_events', 'is_transfer')
    op.drop_column('call_events', 'last_called')
    op.drop_column('call_events', 'transfer_from')
    op.drop_column('call_events', 'scheme_number')
    op.drop_column('call_events', 'scheme_name')
    op.drop_column('call_events', 'call_answer_timestamp')
    # Note: PostgreSQL doesn't support removing enum values
