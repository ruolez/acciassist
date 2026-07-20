"""question phase + follow-up completion timestamp

Revision ID: d7a2e5b9f4c8
Revises: c4f8b2d6e9a1
Create Date: 2026-07-20 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a2e5b9f4c8'
down_revision: str | None = 'c4f8b2d6e9a1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'questions',
        sa.Column('phase', sa.String(length=10), nullable=False, server_default='initial'),
    )
    op.add_column(
        'intake_sessions',
        sa.Column('followup_completed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('intake_sessions', 'followup_completed_at')
    op.drop_column('questions', 'phase')
