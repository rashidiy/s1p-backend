"""Create all tables from scratch

Revision ID: initial
Revises: None
Create Date: 2026-03-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create all PostgreSQL enum types (raw SQL for async compatibility)
    # ------------------------------------------------------------------
    enums = [
        ("provider_enum", "'sipuni', 'binotel'"),
        ("role_enum", "'owner', 'company_admin', 'company_manager', 'company_operator'"),
        ("lead_status_enum", "'new', 'contacted', 'qualified', 'converted', 'lost'"),
        ("pipeline_stage_enum", "'new', 'contact_made', 'meeting_scheduled', 'proposal_sent', 'negotiation', 'won', 'lost'"),
        ("deal_stage_enum", "'prospecting', 'qualification', 'proposal', 'negotiation', 'closed_won', 'closed_lost'"),
        ("task_status_enum", "'pending', 'in_progress', 'completed', 'cancelled'"),
        ("task_priority_enum", "'low', 'medium', 'high', 'urgent'"),
        ("call_direction_enum", "'inbound', 'outbound', 'internal'"),
        ("call_status_enum", "'RINGING', 'ANSWER', 'BUSY', 'NOANSWER', 'CANCEL', 'CONGESTION', 'CHANUNAVAIL'"),
        ("call_outcome_enum", "'interested', 'appointment_scheduled', 'follow_up', 'sale_made', 'no_answer', 'left_voicemail', 'busy', 'callback_requested', 'information_provided', 'not_interested', 'wrong_number', 'do_not_call', 'customer_complaint', 'other'"),
        ("contract_status_enum", "'active', 'warning', 'grace_period', 'expired', 'suspended', 'cancelled'"),
        ("billing_period_enum", "'monthly', 'yearly'"),
        ("payment_status_enum", "'paid', 'pending', 'overdue', 'failed'"),
        ("custom_field_type_enum", "'text', 'number', 'dropdown', 'date', 'boolean'"),
        ("callstatusenum", "'RINGING', 'ANSWER', 'BUSY', 'NOANSWER', 'CANCEL', 'CONGESTION', 'CHANUNAVAIL'"),
    ]
    for name, values in enums:
        op.execute(sa.text(f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({values}); EXCEPTION WHEN duplicate_object THEN NULL; END $$;"))

    # ------------------------------------------------------------------
    # 2. Create tables (ordered by foreign key dependencies)
    # ------------------------------------------------------------------

    # --- owners (no FK dependencies) ---
    op.create_table(
        'owners',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(225), nullable=True),
        sa.Column('last_name', sa.String(225), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_suspended', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_owners_email', 'owners', ['email'], unique=True)

    # --- companies (FK -> owners) ---
    op.create_table(
        'companies',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('subdomain', sa.String(100), nullable=False),
        sa.Column('provider_type', postgresql.ENUM('sipuni', 'binotel', name='provider_enum', create_type=False), nullable=False),
        sa.Column('provider_config', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('webhook_token', sa.String(64), nullable=True),
        sa.Column('timezone', sa.String(50), nullable=True),
        sa.Column('locale', sa.String(10), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_companies_owner_id', 'companies', ['owner_id'])
    op.create_index('ix_companies_subdomain', 'companies', ['subdomain'], unique=True)
    op.create_index('ix_companies_provider_type', 'companies', ['provider_type'])
    op.create_index('ix_companies_webhook_token', 'companies', ['webhook_token'], unique=True)

    # --- permission_groups (FK -> companies) ---
    op.create_table(
        'permission_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'name', name='uq_permission_group_company_name'),
    )
    op.create_index('idx_permission_groups_company_id', 'permission_groups', ['company_id'])

    # --- users (FK -> companies, permission_groups) ---
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('telegram_username', sa.String(225), nullable=True),
        sa.Column('telegram_first_name', sa.String(225), nullable=True),
        sa.Column('telegram_last_name', sa.String(225), nullable=True),
        sa.Column('telegram_avatar_file_id', sa.String(225), nullable=True),
        sa.Column('avatar', sa.String(255), nullable=True),
        sa.Column('avatar_is_custom', sa.Boolean(), server_default=sa.text("'false'"), nullable=True),
        sa.Column('telegram_dm_prefs', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('first_name', sa.String(225), nullable=False),
        sa.Column('last_name', sa.String(225), nullable=True),
        sa.Column('email', sa.String(225), nullable=True),
        sa.Column('phone', sa.String(50), nullable=False),
        sa.Column('sip_extension', sa.String(20), nullable=True),
        sa.Column('password_hash', sa.String(225), nullable=True),
        sa.Column('role', postgresql.ENUM('owner', 'company_admin', 'company_manager', 'company_operator', name='role_enum', create_type=False), nullable=False),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('language', sa.String(10), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_suspended', sa.Boolean(), nullable=True),
        sa.Column('is_shadow', sa.Boolean(), server_default=sa.text("'false'"), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('permission_group_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_group_id'], ['permission_groups.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'email', name='uq_company_email'),
        sa.UniqueConstraint('company_id', 'telegram_user_id', name='uq_company_telegram_user_id'),
    )
    op.create_index('idx_users_company_id', 'users', ['company_id'])
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_role', 'users', ['role'])
    op.create_index('idx_users_telegram_user_id', 'users', ['telegram_user_id'])
    op.create_index(
        'uq_company_phone_not_empty',
        'users',
        ['company_id', 'phone'],
        unique=True,
        postgresql_where=sa.text("phone != '' AND phone IS NOT NULL"),
    )

    op.create_index('idx_users_permission_group_id', 'users', ['permission_group_id'])

    # --- contacts (FK -> companies, users) ---
    op.create_table(
        'contacts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('first_name', sa.String(255), nullable=True),
        sa.Column('last_name', sa.String(255), nullable=True),
        sa.Column('company_name', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('position', sa.String(255), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_contacts_company_id', 'contacts', ['company_id'])
    op.create_index('idx_contacts_company_active', 'contacts', ['company_id', 'deleted_at'])
    op.create_index('idx_contacts_phone', 'contacts', ['phone'])
    op.create_index('idx_contacts_email', 'contacts', ['email'])
    op.create_index('idx_contacts_assigned_to', 'contacts', ['assigned_to'])
    op.create_index('idx_contacts_created_by', 'contacts', ['created_by'])

    # --- leads (FK -> companies, contacts, users) ---
    op.create_table(
        'leads',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('status', postgresql.ENUM('new', 'contacted', 'qualified', 'converted', 'lost', name='lead_status_enum', create_type=False), nullable=False),
        sa.Column('pipeline_stage', postgresql.ENUM('new', 'contact_made', 'meeting_scheduled', 'proposal_sent', 'negotiation', 'won', 'lost', name='pipeline_stage_enum', create_type=False), nullable=False),
        sa.Column('estimated_value', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_leads_company_id', 'leads', ['company_id'])
    op.create_index('idx_leads_company_active', 'leads', ['company_id', 'deleted_at'])
    op.create_index('idx_leads_company_status', 'leads', ['company_id', 'status', 'deleted_at'])
    op.create_index('idx_leads_contact_id', 'leads', ['contact_id'])
    op.create_index('idx_leads_assigned_to', 'leads', ['assigned_to'])
    op.create_index('idx_leads_status', 'leads', ['status'])
    op.create_index('idx_leads_pipeline_stage', 'leads', ['pipeline_stage'])

    # --- deals (FK -> companies, leads, contacts, users) ---
    op.create_table(
        'deals',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column('currency', sa.String(10), nullable=True),
        sa.Column('stage', postgresql.ENUM('prospecting', 'qualification', 'proposal', 'negotiation', 'closed_won', 'closed_lost', name='deal_stage_enum', create_type=False), nullable=False),
        sa.Column('probability', sa.Integer(), nullable=True),
        sa.Column('win_reason', sa.String(), nullable=True),
        sa.Column('loss_reason', sa.String(), nullable=True),
        sa.Column('expected_close_date', sa.Date(), nullable=True),
        sa.Column('closed_date', sa.Date(), nullable=True),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_deals_company_id', 'deals', ['company_id'])
    op.create_index('idx_deals_company_active', 'deals', ['company_id', 'deleted_at'])
    op.create_index('idx_deals_company_stage', 'deals', ['company_id', 'stage', 'deleted_at'])
    op.create_index('idx_deals_lead_id', 'deals', ['lead_id'])
    op.create_index('idx_deals_contact_id', 'deals', ['contact_id'])
    op.create_index('idx_deals_assigned_to', 'deals', ['assigned_to'])
    op.create_index('idx_deals_stage', 'deals', ['stage'])

    # --- call_events (FK -> companies, users, contacts, leads, deals) ---
    op.create_table(
        'call_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider_type', postgresql.ENUM('sipuni', 'binotel', name='provider_enum', create_type=False), nullable=False),
        sa.Column('provider_call_id', sa.String(255), nullable=False),
        sa.Column('phone_1', sa.String(50), nullable=True),
        sa.Column('phone_2', sa.String(50), nullable=True),
        sa.Column('operator_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('direction', postgresql.ENUM('inbound', 'outbound', 'internal', name='call_direction_enum', create_type=False), nullable=True),
        sa.Column('state', postgresql.ENUM('RINGING', 'ANSWER', 'BUSY', 'NOANSWER', 'CANCEL', 'CONGESTION', 'CHANUNAVAIL', name='call_status_enum', create_type=False), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=True),
        sa.Column('waiting_sec', sa.Integer(), nullable=True),
        sa.Column('billing_sec', sa.Integer(), nullable=True),
        sa.Column('record_url', sa.Text(), nullable=True),
        sa.Column('call_start_timestamp', sa.BigInteger(), nullable=True),
        sa.Column('call_end_timestamp', sa.BigInteger(), nullable=True),
        sa.Column('call_answer_timestamp', sa.BigInteger(), nullable=True),
        sa.Column('scheme_name', sa.String(255), nullable=True),
        sa.Column('scheme_number', sa.String(100), nullable=True),
        sa.Column('transfer_from', sa.String(50), nullable=True),
        sa.Column('last_called', sa.String(50), nullable=True),
        sa.Column('is_transfer', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('lead_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('deal_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('outcome', postgresql.ENUM('interested', 'appointment_scheduled', 'follow_up', 'sale_made', 'no_answer', 'left_voicemail', 'busy', 'callback_requested', 'information_provided', 'not_interested', 'wrong_number', 'do_not_call', 'customer_complaint', 'other', name='call_outcome_enum', create_type=False), nullable=True),
        sa.Column('disposition_notes', sa.Text(), nullable=True),
        sa.Column('utm_source', sa.String(255), nullable=True),
        sa.Column('utm_medium', sa.String(255), nullable=True),
        sa.Column('utm_campaign', sa.String(255), nullable=True),
        sa.Column('company_number', sa.String(50), nullable=True),
        sa.Column('order_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['operator_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'provider_type', 'provider_call_id', name='uq_company_provider_call'),
    )
    op.create_index('idx_call_events_company_id', 'call_events', ['company_id'])
    op.create_index('idx_call_events_operator_id', 'call_events', ['operator_id'])
    op.create_index('idx_call_events_contact_id', 'call_events', ['contact_id'])
    op.create_index('idx_call_events_lead_id', 'call_events', ['lead_id'])
    op.create_index('idx_call_events_phone_1', 'call_events', ['phone_1'])
    op.create_index('idx_call_events_phone_2', 'call_events', ['phone_2'])
    op.create_index('idx_call_events_created_at', 'call_events', ['created_at'])

    # --- tasks (FK -> companies, users) ---
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'in_progress', 'completed', 'cancelled', name='task_status_enum', create_type=False), nullable=False),
        sa.Column('priority', postgresql.ENUM('low', 'medium', 'high', 'urgent', name='task_priority_enum', create_type=False), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_tasks_company_id', 'tasks', ['company_id'])
    op.create_index('idx_tasks_company_active', 'tasks', ['company_id', 'deleted_at'])
    op.create_index('idx_tasks_assigned_to', 'tasks', ['assigned_to'])
    op.create_index('idx_tasks_created_by', 'tasks', ['created_by'])
    op.create_index('idx_tasks_status', 'tasks', ['status'])
    op.create_index('idx_tasks_due_date', 'tasks', ['due_date'])
    op.create_index('idx_tasks_entity', 'tasks', ['entity_type', 'entity_id'])

    # --- notes (FK -> companies, users) ---
    op.create_table(
        'notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=False),
        sa.Column('entity_id', sa.String(255), nullable=False),
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_notes_company_id', 'notes', ['company_id'])
    op.create_index('idx_notes_created_by', 'notes', ['created_by'])
    op.create_index('idx_notes_entity', 'notes', ['entity_type', 'entity_id'])

    # --- tags (FK -> companies) ---
    op.create_table(
        'tags',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('color', sa.String(7), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'name', name='uq_company_tag_name'),
    )
    op.create_index('idx_tags_company_id', 'tags', ['company_id'])

    # --- contracts (FK -> owners, companies) ---
    op.create_table(
        'contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('max_admins', sa.Integer(), nullable=False),
        sa.Column('max_managers', sa.Integer(), nullable=False),
        sa.Column('max_operators', sa.Integer(), nullable=False),
        sa.Column('max_storage_gb', sa.Integer(), nullable=False),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('billing_period', postgresql.ENUM('monthly', 'yearly', name='billing_period_enum', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('active', 'warning', 'grace_period', 'expired', 'suspended', 'cancelled', name='contract_status_enum', create_type=False), nullable=False),
        sa.Column('payment_status', postgresql.ENUM('paid', 'pending', 'overdue', 'failed', name='payment_status_enum', create_type=False), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('next_payment_date', sa.Date(), nullable=True),
        sa.Column('grace_period_days', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('auto_renew', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_contracts_company_id', 'contracts', ['company_id'])
    op.create_index('idx_contracts_owner_id', 'contracts', ['owner_id'])
    op.create_index('idx_contracts_status', 'contracts', ['status'])
    op.create_index('idx_contracts_end_date', 'contracts', ['end_date'])

    # --- audit_logs (FK -> companies, users) ---
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_audit_logs_company_id', 'audit_logs', ['company_id'])
    op.create_index('idx_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('idx_audit_logs_entity', 'audit_logs', ['entity_type', 'entity_id'])
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])

    # --- custom_field_definitions (FK -> companies) ---
    op.create_table(
        'custom_field_definitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('field_name', sa.String(100), nullable=False),
        sa.Column('field_type', postgresql.ENUM('text', 'number', 'dropdown', 'date', 'boolean', name='custom_field_type_enum', create_type=False), nullable=False),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_required', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'entity_type', 'field_name', name='uq_company_entity_field_name'),
    )
    op.create_index('idx_cfd_company_id', 'custom_field_definitions', ['company_id'])
    op.create_index('idx_cfd_company_entity', 'custom_field_definitions', ['company_id', 'entity_type'])

    # --- api_keys (FK -> companies) ---
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False),
        sa.Column('key_prefix', sa.String(8), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_api_keys_key_hash', 'api_keys', ['key_hash'], unique=True)
    op.create_index('idx_api_keys_company_id', 'api_keys', ['company_id'])

    # --- webhook_endpoints (FK -> companies) ---
    op.create_table(
        'webhook_endpoints',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('url', sa.String(2048), nullable=False),
        sa.Column('events', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('secret', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_webhook_endpoints_company_id', 'webhook_endpoints', ['company_id'])
    op.create_index('idx_webhook_endpoints_active', 'webhook_endpoints', ['is_active'])

    # --- webhook_deliveries (FK -> webhook_endpoints) ---
    op.create_table(
        'webhook_deliveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('endpoint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('response_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['endpoint_id'], ['webhook_endpoints.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_webhook_deliveries_endpoint_id', 'webhook_deliveries', ['endpoint_id'])
    op.create_index('idx_webhook_deliveries_status', 'webhook_deliveries', ['status'])
    op.create_index('idx_webhook_deliveries_created_at', 'webhook_deliveries', ['created_at'])

    # --- telegram_bot_configs (FK -> companies) ---
    op.create_table(
        'telegram_bot_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('chat_id', sa.String(100), nullable=True),
        sa.Column('group_chat_id', sa.BigInteger(), nullable=True),
        sa.Column('topic_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('invite_link', sa.String(255), nullable=True),
        sa.Column('setup_status', sa.String(20), server_default=sa.text("'not_started'"), nullable=False),
        sa.Column('setup_error', sa.Text(), nullable=True),
        sa.Column('group_name', sa.String(255), nullable=True),
        sa.Column('language', sa.String(10), server_default=sa.text("'ru'"), nullable=False),
        sa.Column('send_recordings', sa.Boolean(), server_default=sa.text("'true'"), nullable=False),
        sa.Column('daily_digest', sa.Boolean(), server_default=sa.text("'true'"), nullable=False),
        sa.Column('dm_notifications', sa.Boolean(), server_default=sa.text("'false'"), nullable=False),
        sa.Column('digest_message_id', sa.Integer(), nullable=True),
        sa.Column('notification_filters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text(
            "'{\"call_completed\": true, \"call_missed\": true, "
            "\"new_lead\": true, \"deal_stage_change\": true}'::jsonb"
        ), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_telegram_bot_configs_company_id', 'telegram_bot_configs', ['company_id'], unique=True)
    op.create_index('ix_telegram_bot_configs_chat_id', 'telegram_bot_configs', ['chat_id'])

    # --- sipuni_setup_configs (FK -> companies) ---
    op.create_table(
        'sipuni_setup_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('setup_status', sa.String(20), server_default=sa.text("'not_started'"), nullable=False),
        sa.Column('setup_error', sa.Text(), nullable=True),
        sa.Column('setup_method', sa.String(20), nullable=True),
        sa.Column('services_enabled', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sipuni_setup_configs_company_id', 'sipuni_setup_configs', ['company_id'], unique=True)

    # --- invite_tokens (FK -> companies, permission_groups, users) ---
    op.create_table(
        'invite_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('role', postgresql.ENUM('owner', 'company_admin', 'company_manager', 'company_operator', name='role_enum', create_type=False), nullable=False),
        sa.Column('first_name', sa.String(225), nullable=True),
        sa.Column('last_name', sa.String(225), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('sip_extension', sa.String(20), nullable=True),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('permission_group_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_group_id'], ['permission_groups.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['used_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_invite_tokens_company_id', 'invite_tokens', ['company_id'])
    op.create_index('idx_invite_tokens_token_hash', 'invite_tokens', ['token_hash'])
    op.create_index('idx_invite_tokens_created_by', 'invite_tokens', ['created_by'])

    # --- telegram_auth_challenges (FK -> companies, users, invite_tokens) ---
    op.create_table(
        'telegram_auth_challenges',
        sa.Column('id', sa.String(32), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('otp_hash', sa.String(64), nullable=True),
        sa.Column('purpose', sa.String(10), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('used', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('telegram_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('invite_token_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invite_token_id'], ['invite_tokens.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_tac_company_id', 'telegram_auth_challenges', ['company_id'])

    # --- sipuni (legacy, FK -> users) ---
    op.create_table(
        'sipuni',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_name', sa.String(255), nullable=False),
        sa.Column('cabinet_id', sa.String(25), nullable=False),
        sa.Column('security_key', sa.String(255), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token', sa.String(64), nullable=False),
        sa.Column('partner_name', sa.String(255), nullable=True),
        sa.Column('partner_contact', sa.String(255), nullable=True),
        sa.Column('comment', sa.String(1024), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'cabinet_id'),
        sa.UniqueConstraint('token'),
    )

    # --- sipuni_call_events (legacy, FK -> sipuni) ---
    op.create_table(
        'sipuni_call_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('call_id', sa.String(255), nullable=True),
        sa.Column('call_start_timestamp', sa.BigInteger(), nullable=True),
        sa.Column('call_end_timestamp', sa.BigInteger(), nullable=True),
        sa.Column('sipuni_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('pbxdstnum', sa.String(255), nullable=True),
        sa.Column('dst_type', sa.String(1), nullable=True),
        sa.Column('src_num', sa.String(255), nullable=True),
        sa.Column('src_type', sa.String(1), nullable=True),
        sa.Column('last_called', postgresql.ARRAY(sa.String(255)), nullable=True),
        sa.Column('transfer_from', sa.String(255), nullable=True),
        sa.Column('tree_number', sa.String(255), nullable=True),
        sa.Column('record_link', sa.String(2048), nullable=True),
        sa.Column('timestamp', sa.BigInteger(), nullable=True),
        sa.Column('status', postgresql.ENUM('RINGING', 'ANSWER', 'BUSY', 'NOANSWER', 'CANCEL', 'CONGESTION', 'CHANUNAVAIL', name='callstatusenum', create_type=False), nullable=True),
        sa.ForeignKeyConstraint(['sipuni_id'], ['sipuni.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('call_id'),
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Drop tables in reverse dependency order
    # ------------------------------------------------------------------
    op.drop_table('sipuni_call_events')
    op.drop_table('sipuni')
    op.drop_table('telegram_auth_challenges')
    op.drop_table('invite_tokens')
    op.drop_table('sipuni_setup_configs')
    op.drop_table('telegram_bot_configs')
    op.drop_table('webhook_deliveries')
    op.drop_table('webhook_endpoints')
    op.drop_table('api_keys')
    op.drop_table('custom_field_definitions')
    op.drop_table('audit_logs')
    op.drop_table('contracts')
    op.drop_table('tags')
    op.drop_table('notes')
    op.drop_table('tasks')
    op.drop_table('call_events')
    op.drop_table('deals')
    op.drop_table('leads')
    op.drop_table('contacts')
    op.drop_table('users')
    op.drop_table('permission_groups')
    op.drop_table('companies')
    op.drop_table('owners')

    # ------------------------------------------------------------------
    # Drop all enum types
    # ------------------------------------------------------------------
    for name in [
        'callstatusenum', 'custom_field_type_enum', 'payment_status_enum',
        'billing_period_enum', 'contract_status_enum', 'call_outcome_enum',
        'call_status_enum', 'call_direction_enum', 'task_priority_enum',
        'task_status_enum', 'deal_stage_enum', 'pipeline_stage_enum',
        'lead_status_enum', 'role_enum', 'provider_enum',
    ]:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {name};"))
