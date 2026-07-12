"""jurisdiction rules

Revision ID: e5b8a2c6d4f1
Revises: b7c4e2a91f56
Create Date: 2026-07-12 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b8a2c6d4f1'
down_revision: str | None = 'b7c4e2a91f56'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('jurisdiction_rules',
    sa.Column('state_code', sa.String(length=2), nullable=False),
    sa.Column('state_name', sa.String(length=50), nullable=False),
    sa.Column('comparative_rule', sa.String(length=20), nullable=False),
    sa.Column('no_fault', sa.Boolean(), nullable=False),
    sa.Column('pip_threshold_note', sa.Text(), nullable=True),
    sa.Column('sol_years_pi', sa.Float(), nullable=False),
    sa.Column('sol_note', sa.Text(), nullable=True),
    sa.Column('noneconomic_cap', sa.Integer(), nullable=True),
    sa.Column('cap_note', sa.Text(), nullable=True),
    sa.Column('collateral_source_note', sa.Text(), nullable=True),
    sa.Column('needs_review', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('state_code')
    )


def downgrade() -> None:
    op.drop_table('jurisdiction_rules')
