"""replace UUID with integer id for call_events

Revision ID: replace_uuid_with_int_id
Revises: add_call_number
Create Date: 2026-02-16

Removes UUID primary key from call_events, promotes call_number to id (Integer PK).
Changes notes.entity_id from UUID to String(255) for polymorphic support.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'replace_uuid_with_int_id'
down_revision: Union[str, None] = 'add_call_number'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- notes.entity_id: UUID -> String(255) ---
    # Clean up notes referencing calls (they store UUID entity_ids that will be invalid)
    op.execute("DELETE FROM notes WHERE entity_type = 'call'")

    # Cast existing UUID entity_id values to text
    op.execute("ALTER TABLE notes ALTER COLUMN entity_id TYPE VARCHAR(255) USING entity_id::text")

    # Drop index on entity columns (will be recreated)
    op.drop_index('idx_notes_entity', table_name='notes')
    op.create_index('idx_notes_entity', 'notes', ['entity_type', 'entity_id'])

    # --- call_events: UUID id -> Integer id (from call_number) ---

    # Drop old constraints and indexes that reference the UUID id or call_number
    op.drop_constraint('uq_company_provider_call', 'call_events', type_='unique')
    op.drop_constraint('uq_company_call_number', 'call_events', type_='unique')
    op.drop_index('idx_call_events_call_number', table_name='call_events')

    # Drop the UUID primary key
    op.drop_constraint('call_events_pkey', 'call_events', type_='primary')

    # Drop the old UUID id column
    op.drop_column('call_events', 'id')

    # Rename call_number to id
    op.alter_column('call_events', 'call_number', new_column_name='id')

    # Add primary key on the new integer id
    op.create_primary_key('call_events_pkey', 'call_events', ['id'])

    # Recreate the unique constraint for provider deduplication
    op.create_unique_constraint(
        'uq_company_provider_call', 'call_events',
        ['company_id', 'provider_type', 'provider_call_id']
    )


def downgrade() -> None:
    # Drop new PK
    op.drop_constraint('call_events_pkey', 'call_events', type_='primary')

    # Rename id back to call_number
    op.alter_column('call_events', 'id', new_column_name='call_number')

    # Add UUID id column back
    op.add_column(
        'call_events',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                   server_default=sa.text("gen_random_uuid()"), nullable=False)
    )

    # Restore PK on UUID id
    op.create_primary_key('call_events_pkey', 'call_events', ['id'])

    # Restore call_number unique constraint and index
    op.create_unique_constraint(
        'uq_company_call_number', 'call_events',
        ['company_id', 'call_number']
    )
    op.create_index('idx_call_events_call_number', 'call_events', ['call_number'])

    # Restore provider unique constraint
    op.drop_constraint('uq_company_provider_call', 'call_events', type_='unique')
    op.create_unique_constraint(
        'uq_company_provider_call', 'call_events',
        ['company_id', 'provider_type', 'provider_call_id']
    )

    # --- notes.entity_id: String(255) -> UUID ---
    # Delete any notes with non-UUID entity_ids
    op.execute("""
        DELETE FROM notes
        WHERE entity_id !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    """)

    op.drop_index('idx_notes_entity', table_name='notes')
    op.execute("ALTER TABLE notes ALTER COLUMN entity_id TYPE UUID USING entity_id::uuid")
    op.create_index('idx_notes_entity', 'notes', ['entity_type', 'entity_id'])
