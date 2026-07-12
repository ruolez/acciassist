"""estimate pipeline columns

Revision ID: a9d4e6f8b2c3
Revises: f2c7d9e4a8b5
Create Date: 2026-07-12 15:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'a9d4e6f8b2c3'
down_revision: str | None = 'f2c7d9e4a8b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('case_estimates', sa.Column('gross_min', sa.Integer(), nullable=True))
    op.add_column('case_estimates', sa.Column('gross_max', sa.Integer(), nullable=True))
    op.add_column('case_estimates', sa.Column('net_min', sa.Integer(), nullable=True))
    op.add_column('case_estimates', sa.Column('net_max', sa.Integer(), nullable=True))
    op.add_column('case_estimates', sa.Column('result', JSONB(), nullable=True))
    op.add_column('case_estimates', sa.Column('internals', JSONB(), nullable=True))
    op.add_column('case_estimates', sa.Column('stage_status', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('case_estimates', 'stage_status')
    op.drop_column('case_estimates', 'internals')
    op.drop_column('case_estimates', 'result')
    op.drop_column('case_estimates', 'net_max')
    op.drop_column('case_estimates', 'net_min')
    op.drop_column('case_estimates', 'gross_max')
    op.drop_column('case_estimates', 'gross_min')
