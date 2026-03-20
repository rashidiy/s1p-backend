"""add sip_extension to users and invite_tokens

Revision ID: add_sip_extension
Revises: add_call_event_webhook_fields
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'add_sip_extension'
down_revision: Union[str, None] = 'add_call_event_webhook_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('sip_extension', sa.String(20), nullable=True))
    op.add_column('invite_tokens', sa.Column('sip_extension', sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column('invite_tokens', 'sip_extension')
    op.drop_column('users', 'sip_extension')
