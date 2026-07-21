"""openrouter provisioning key

Revision ID: e8b4d2f6a1c9
Revises: c7e2f9a4b6d3
Create Date: 2026-07-21 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b4d2f6a1c9'
down_revision: str | None = 'c7e2f9a4b6d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'app_settings',
        sa.Column('openrouter_provisioning_key', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('app_settings', 'openrouter_provisioning_key')
