"""merge telegram auth and win loss reason

Revision ID: 50b7be049558
Revises: add_telegram_auth, add_win_loss_reason
Create Date: 2026-03-12 02:32:17.247414

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50b7be049558'
down_revision: Union[str, None] = ('add_telegram_auth', 'add_win_loss_reason')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
