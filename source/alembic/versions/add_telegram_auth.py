"""add telegram auth models

Revision ID: add_telegram_auth
Revises: 86e897b0e86c
Create Date: 2026-03-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_telegram_auth'
down_revision: Union[str, None] = '86e897b0e86c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add telegram auth columns and tables."""

    # 1. Add telegram_user_id to users table
    op.add_column('users', sa.Column('telegram_user_id', sa.BigInteger(), nullable=True))
    op.create_index('idx_users_telegram_user_id', 'users', ['telegram_user_id'])
    op.create_unique_constraint('uq_users_telegram_user_id', 'users', ['telegram_user_id'])

    # 2. Make email nullable
    op.alter_column('users', 'email',
                    existing_type=sa.String(225),
                    nullable=True)

    # 3. Make password_hash nullable
    op.alter_column('users', 'password_hash',
                    existing_type=sa.String(225),
                    nullable=True)

    # 4. Backfill empty phone values before adding NOT NULL constraint
    op.execute("UPDATE users SET phone = '' WHERE phone IS NULL")

    # 5. Make phone NOT NULL
    op.alter_column('users', 'phone',
                    existing_type=sa.String(50),
                    nullable=False)

    # 6. Add partial unique index for company_id + phone (only when phone is not empty)
    op.create_index(
        'uq_company_phone_not_empty',
        'users',
        ['company_id', 'phone'],
        unique=True,
        postgresql_where=text("phone != '' AND phone IS NOT NULL"),
    )

    # 7. Create invite_tokens table
    op.create_table(
        'invite_tokens',
        sa.Column('id', sa.UUID(), default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('role', sa.Enum('owner', 'company_admin', 'company_manager', 'company_operator',
                                  name='role_enum', create_type=False), nullable=False),
        sa.Column('first_name', sa.String(225), nullable=False),
        sa.Column('last_name', sa.String(225), nullable=True),
        sa.Column('phone', sa.String(50), nullable=False),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()),
                  server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('permission_group_id', sa.UUID(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_group_id'], ['permission_groups.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['used_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_invite_tokens_company_id', 'invite_tokens', ['company_id'])
    op.create_index('idx_invite_tokens_token_hash', 'invite_tokens', ['token_hash'])
    op.create_index('idx_invite_tokens_created_by', 'invite_tokens', ['created_by'])

    # 8. Create telegram_auth_challenges table
    op.create_table(
        'telegram_auth_challenges',
        sa.Column('id', sa.String(32), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('otp_hash', sa.String(64), nullable=True),
        sa.Column('purpose', sa.String(10), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('used', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_tac_company_id', 'telegram_auth_challenges', ['company_id'])


def downgrade() -> None:
    """Remove telegram auth columns and tables."""
    op.drop_table('telegram_auth_challenges')
    op.drop_index('idx_invite_tokens_created_by', table_name='invite_tokens')
    op.drop_index('idx_invite_tokens_token_hash', table_name='invite_tokens')
    op.drop_index('idx_invite_tokens_company_id', table_name='invite_tokens')
    op.drop_table('invite_tokens')

    op.drop_index('uq_company_phone_not_empty', table_name='users')
    op.alter_column('users', 'phone', existing_type=sa.String(50), nullable=True)
    op.alter_column('users', 'password_hash', existing_type=sa.String(225), nullable=False)
    op.alter_column('users', 'email', existing_type=sa.String(225), nullable=False)
    op.drop_constraint('uq_users_telegram_user_id', 'users', type_='unique')
    op.drop_index('idx_users_telegram_user_id', table_name='users')
    op.drop_column('users', 'telegram_user_id')
