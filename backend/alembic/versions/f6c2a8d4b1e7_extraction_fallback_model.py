"""extraction fallback model

Revision ID: f6c2a8d4b1e7
Revises: e8b4d2f6a1c9
Create Date: 2026-07-21 22:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6c2a8d4b1e7'
down_revision: str | None = 'e8b4d2f6a1c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'app_settings',
        sa.Column('extraction_fallback_model', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('app_settings', 'extraction_fallback_model')
