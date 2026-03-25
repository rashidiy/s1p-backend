"""Add stats.read permission to existing operator users

Revision ID: add_stats_read_to_operators
Revises: add_failed_call_status
Create Date: 2026-03-25

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'add_stats_read_to_operators'
down_revision = 'add_failed_call_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE users
        SET permissions = permissions || '["stats.read"]'::jsonb
        WHERE role = 'company_operator'
          AND NOT (permissions @> '["stats.read"]'::jsonb)
          AND deleted_at IS NULL
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE users
        SET permissions = (
            SELECT jsonb_agg(elem)
            FROM jsonb_array_elements(permissions) elem
            WHERE elem::text != '"stats.read"'
        )
        WHERE role = 'company_operator'
          AND permissions @> '["stats.read"]'::jsonb
    """)
