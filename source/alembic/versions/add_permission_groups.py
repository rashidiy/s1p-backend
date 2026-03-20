"""add_permission_groups

Revision ID: add_permission_groups
Revises: 848cafadb806
Create Date: 2026-02-10

Creates permission_groups table, adds permission_group_id FK to users,
and seeds 3 system groups (admin, manager, operator).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_permission_groups'
down_revision: Union[str, None] = '848cafadb806'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create permission_groups table
    op.create_table(
        'permission_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'name', name='uq_permission_group_company_name'),
    )
    op.create_index('idx_permission_groups_company_id', 'permission_groups', ['company_id'], unique=False)

    # Partial unique index for system group names (WHERE company_id IS NULL)
    op.execute(
        "CREATE UNIQUE INDEX uq_permission_group_system_name "
        "ON permission_groups (name) WHERE company_id IS NULL"
    )

    # Add permission_group_id column to users
    op.add_column('users', sa.Column('permission_group_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_users_permission_group_id',
        'users', 'permission_groups',
        ['permission_group_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index('idx_users_permission_group_id', 'users', ['permission_group_id'], unique=False)

    # Seed system permission groups with deterministic UUIDs
    op.execute("""
        INSERT INTO permission_groups (id, company_id, name, description, permissions, is_system)
        VALUES
        (
            '00000000-0000-0000-0000-000000000001',
            NULL,
            'admin',
            'Default permissions for Company Admin role',
            '["leads.read","leads.write","leads.delete","leads.assign","contacts.read","contacts.write","contacts.delete","contacts.import","contacts.export","deals.read","deals.write","deals.delete","deals.assign","tasks.read","tasks.write","tasks.delete","tasks.assign","calls.read","calls.write","calls.make","notes.read","notes.write","notes.delete","users.read","users.create","users.update","users.write","users.delete","users.manage","stats.read","stats.export","settings.read","settings.manage","company.read","company.manage","contract.read"]'::jsonb,
            true
        ),
        (
            '00000000-0000-0000-0000-000000000002',
            NULL,
            'manager',
            'Default permissions for Company Manager role',
            '["leads.read","leads.write","leads.assign","contacts.read","contacts.write","contacts.import","contacts.export","deals.read","deals.write","deals.assign","tasks.read","tasks.write","tasks.assign","calls.read","calls.write","calls.make","notes.read","notes.write","users.read","stats.read","settings.read","company.read"]'::jsonb,
            true
        ),
        (
            '00000000-0000-0000-0000-000000000003',
            NULL,
            'operator',
            'Default permissions for Company Operator role',
            '["leads.read","contacts.read","deals.read","tasks.read","tasks.write","calls.read","calls.write","calls.make","notes.read","notes.write","company.read"]'::jsonb,
            true
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove permission_group_id from users
    op.drop_index('idx_users_permission_group_id', table_name='users')
    op.drop_constraint('fk_users_permission_group_id', 'users', type_='foreignkey')
    op.drop_column('users', 'permission_group_id')

    # Drop permission_groups table
    op.execute("DROP INDEX IF EXISTS uq_permission_group_system_name")
    op.drop_index('idx_permission_groups_company_id', table_name='permission_groups')
    op.drop_table('permission_groups')
