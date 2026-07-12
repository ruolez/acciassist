"""estimate pipeline settings

Revision ID: f2c7d9e4a8b5
Revises: e5b8a2c6d4f1
Create Date: 2026-07-12 14:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2c7d9e4a8b5'
down_revision: str | None = 'e5b8a2c6d4f1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('app_settings', sa.Column('comps_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('app_settings', sa.Column('comps_model', sa.String(length=255), nullable=True))
    op.add_column('app_settings', sa.Column('sample_count', sa.Integer(), nullable=False, server_default='5'))
    op.add_column('app_settings', sa.Column('contingency_fee_pct', sa.Float(), nullable=False, server_default='33.3'))


def downgrade() -> None:
    op.drop_column('app_settings', 'contingency_fee_pct')
    op.drop_column('app_settings', 'sample_count')
    op.drop_column('app_settings', 'comps_model')
    op.drop_column('app_settings', 'comps_enabled')
