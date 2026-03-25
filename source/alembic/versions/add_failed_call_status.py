"""Add FAILED to call_status_enum

Revision ID: add_failed_call_status
Revises: add_callback_tracking
Create Date: 2026-03-25

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_failed_call_status'
down_revision = 'add_callback_tracking'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE call_status_enum ADD VALUE IF NOT EXISTS 'FAILED'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values
    pass
