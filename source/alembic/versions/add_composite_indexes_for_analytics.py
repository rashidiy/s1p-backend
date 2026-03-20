"""Add composite indexes for analytics performance

Revision ID: add_composite_indexes
Revises: 661b90dcb396
Create Date: 2026-01-27

These indexes optimize common analytics query patterns:
- Date-range queries on call_events, leads, deals
- Status filtering with date ranges
- User assignment queries
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_composite_indexes'
down_revision = '661b90dcb396'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Call Events - Optimizes analytics date-range queries
    op.create_index(
        'idx_call_events_company_created_at',
        'call_events',
        ['company_id', 'created_at'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_call_events_operator_created_at',
        'call_events',
        ['operator_id', 'created_at'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_call_events_company_state_created_at',
        'call_events',
        ['company_id', 'state', 'created_at'],
        postgresql_using='btree'
    )

    # Leads - Optimizes status filtering and date-range queries
    op.create_index(
        'idx_leads_company_status_created_at',
        'leads',
        ['company_id', 'status', 'created_at'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_leads_assigned_to_status',
        'leads',
        ['assigned_to', 'status'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_leads_contact_deleted',
        'leads',
        ['contact_id', 'deleted_at'],
        postgresql_using='btree'
    )

    # Deals - Optimizes pipeline and revenue queries
    op.create_index(
        'idx_deals_company_stage_created_at',
        'deals',
        ['company_id', 'stage', 'created_at'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_deals_assigned_to_stage',
        'deals',
        ['assigned_to', 'stage'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_deals_company_stage_amount',
        'deals',
        ['company_id', 'stage', 'amount'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_deals_contact_deleted',
        'deals',
        ['contact_id', 'deleted_at'],
        postgresql_using='btree'
    )

    # Tasks - Optimizes user task queries
    op.create_index(
        'idx_tasks_assigned_to_status_due_date',
        'tasks',
        ['assigned_to', 'status', 'due_date'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_tasks_company_status_created_at',
        'tasks',
        ['company_id', 'status', 'created_at'],
        postgresql_using='btree'
    )

    # Users - Optimizes team analytics queries
    op.create_index(
        'idx_users_company_role_active',
        'users',
        ['company_id', 'role', 'is_active'],
        postgresql_using='btree'
    )

    # Contacts - Optimizes contact listing with phone lookups
    op.create_index(
        'idx_contacts_company_created_at',
        'contacts',
        ['company_id', 'created_at'],
        postgresql_using='btree'
    )

    # Companies - Optimizes owner platform queries
    op.create_index(
        'idx_companies_owner_active',
        'companies',
        ['owner_id', 'is_active'],
        postgresql_using='btree'
    )


def downgrade() -> None:
    # Call Events
    op.drop_index('idx_call_events_company_created_at', table_name='call_events')
    op.drop_index('idx_call_events_operator_created_at', table_name='call_events')
    op.drop_index('idx_call_events_company_state_created_at', table_name='call_events')

    # Leads
    op.drop_index('idx_leads_company_status_created_at', table_name='leads')
    op.drop_index('idx_leads_assigned_to_status', table_name='leads')
    op.drop_index('idx_leads_contact_deleted', table_name='leads')

    # Deals
    op.drop_index('idx_deals_company_stage_created_at', table_name='deals')
    op.drop_index('idx_deals_assigned_to_stage', table_name='deals')
    op.drop_index('idx_deals_company_stage_amount', table_name='deals')
    op.drop_index('idx_deals_contact_deleted', table_name='deals')

    # Tasks
    op.drop_index('idx_tasks_assigned_to_status_due_date', table_name='tasks')
    op.drop_index('idx_tasks_company_status_created_at', table_name='tasks')

    # Users
    op.drop_index('idx_users_company_role_active', table_name='users')

    # Contacts
    op.drop_index('idx_contacts_company_created_at', table_name='contacts')

    # Companies
    op.drop_index('idx_companies_owner_active', table_name='companies')
