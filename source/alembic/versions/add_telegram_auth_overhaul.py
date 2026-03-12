"""Add telegram auth overhaul: user telegram fields, challenge telegram_data, invite token nullable fields

Revision ID: add_telegram_auth_overhaul
Revises: 50b7be049558
Create Date: 2026-03-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = 'add_telegram_auth_overhaul'
down_revision: Union[str, None] = '50b7be049558'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add telegram profile columns to users
    op.add_column('users', sa.Column('telegram_username', sa.String(225), nullable=True))
    op.add_column('users', sa.Column('telegram_first_name', sa.String(225), nullable=True))
    op.add_column('users', sa.Column('telegram_last_name', sa.String(225), nullable=True))
    op.add_column('users', sa.Column('telegram_avatar_file_id', sa.String(225), nullable=True))

    # 2. Change telegram_user_id from globally unique to per-company unique
    # Drop the old unique constraint on telegram_user_id
    op.drop_index('idx_users_telegram_user_id', table_name='users')
    op.drop_constraint('uq_users_telegram_user_id', type_='unique', table_name='users')
    # Create composite unique constraint
    op.create_unique_constraint('uq_company_telegram_user_id', 'users', ['company_id', 'telegram_user_id'])
    # Re-create index (non-unique)
    op.create_index('idx_users_telegram_user_id', 'users', ['telegram_user_id'])

    # 3. Add telegram_data and invite_token_id to telegram_auth_challenges
    op.add_column('telegram_auth_challenges', sa.Column('telegram_data', JSONB, nullable=True))
    op.add_column('telegram_auth_challenges', sa.Column('invite_token_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_tac_invite_token_id',
        'telegram_auth_challenges',
        'invite_tokens',
        ['invite_token_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # 4. Make first_name and phone nullable in invite_tokens
    op.alter_column('invite_tokens', 'first_name', existing_type=sa.String(225), nullable=True)
    op.alter_column('invite_tokens', 'phone', existing_type=sa.String(50), nullable=True)


def downgrade() -> None:
    # Reverse invite_tokens changes
    op.alter_column('invite_tokens', 'phone', existing_type=sa.String(50), nullable=False)
    op.alter_column('invite_tokens', 'first_name', existing_type=sa.String(225), nullable=False)

    # Remove telegram_auth_challenges columns
    op.drop_constraint('fk_tac_invite_token_id', 'telegram_auth_challenges', type_='foreignkey')
    op.drop_column('telegram_auth_challenges', 'invite_token_id')
    op.drop_column('telegram_auth_challenges', 'telegram_data')

    # Reverse telegram_user_id constraint change
    op.drop_index('idx_users_telegram_user_id', table_name='users')
    op.drop_constraint('uq_company_telegram_user_id', type_='unique', table_name='users')
    op.create_unique_constraint('uq_users_telegram_user_id', 'users', ['telegram_user_id'])
    op.create_index('idx_users_telegram_user_id', 'users', ['telegram_user_id'], unique=True)

    # Remove telegram profile columns from users
    op.drop_column('users', 'telegram_avatar_file_id')
    op.drop_column('users', 'telegram_last_name')
    op.drop_column('users', 'telegram_first_name')
    op.drop_column('users', 'telegram_username')
