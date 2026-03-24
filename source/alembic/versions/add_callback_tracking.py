"""Add callback tracking and telegram message tracking to call_events

Revision ID: add_callback_tracking
Revises: initial
Create Date: 2026-03-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_callback_tracking'
down_revision = 'initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('call_events', sa.Column('needs_callback', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('call_events', sa.Column('callback_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('call_events', sa.Column('callback_call_id', sa.Integer(), sa.ForeignKey('call_events.id', ondelete='SET NULL'), nullable=True))
    op.add_column('call_events', sa.Column('telegram_message_id', sa.Integer(), nullable=True))

    # Don't flag old calls — only new calls get needs_callback from webhooks.
    # Flagging old calls causes escalation spam when a Telegram group is first created.


def downgrade() -> None:
    op.drop_column('call_events', 'telegram_message_id')
    op.drop_column('call_events', 'callback_call_id')
    op.drop_column('call_events', 'callback_at')
    op.drop_column('call_events', 'needs_callback')
