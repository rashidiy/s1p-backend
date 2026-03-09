"""merge multiple heads

Revision ID: 86e897b0e86c
Revises: add_created_by_to_leads, add_custom_field_definitions, add_telegram_configs
Create Date: 2026-03-09 05:37:26.017576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86e897b0e86c'
down_revision: Union[str, None] = ('add_created_by_to_leads', 'add_custom_field_definitions', 'add_telegram_configs')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
