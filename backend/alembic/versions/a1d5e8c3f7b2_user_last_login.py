"""user last login

Revision ID: a1d5e8c3f7b2
Revises: f6c2a8d4b1e7
Create Date: 2026-07-21 23:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1d5e8c3f7b2'
down_revision: str | None = 'f6c2a8d4b1e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('users', 'last_login_at')
