"""ai estimates

Revision ID: a3f1c9e7b2d4
Revises: d808b01e3c9c
Create Date: 2026-07-12 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9e7b2d4'
down_revision: str | None = 'd808b01e3c9c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('app_settings', sa.Column('openrouter_api_key', sa.String(length=255), nullable=True))
    op.add_column('app_settings', sa.Column('openrouter_model', sa.String(length=255), nullable=True))
    op.create_table('case_estimates',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('intake_session_id', UUID(as_uuid=True), nullable=False),
    sa.Column('status', sa.Enum('pending', 'completed', 'failed', name='estimate_status'), nullable=False),
    sa.Column('payout_min', sa.Integer(), nullable=True),
    sa.Column('payout_max', sa.Integer(), nullable=True),
    sa.Column('case_cost_min', sa.Integer(), nullable=True),
    sa.Column('case_cost_max', sa.Integer(), nullable=True),
    sa.Column('confidence', sa.String(length=10), nullable=True),
    sa.Column('reasoning', sa.Text(), nullable=True),
    sa.Column('missing_info', JSONB(), nullable=True),
    sa.Column('model', sa.String(length=255), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['intake_session_id'], ['intake_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('intake_session_id')
    )
    op.create_table('estimate_advice',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('injury_type_id', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('model', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['injury_type_id'], ['injury_types.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('injury_type_id')
    )


def downgrade() -> None:
    op.drop_table('estimate_advice')
    op.drop_table('case_estimates')
    sa.Enum(name='estimate_status').drop(op.get_bind(), checkfirst=True)
    op.drop_column('app_settings', 'openrouter_model')
    op.drop_column('app_settings', 'openrouter_api_key')
