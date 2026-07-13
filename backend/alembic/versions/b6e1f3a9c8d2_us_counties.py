"""us counties table + us_state_county question type

Revision ID: b6e1f3a9c8d2
Revises: a9d4e6f8b2c3
Create Date: 2026-07-13 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e1f3a9c8d2'
down_revision: str | None = 'a9d4e6f8b2c3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('us_counties',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('state_code', sa.String(length=2), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('state_code', 'name', name='uq_county_state_name')
    )
    op.create_index('ix_us_counties_state_code', 'us_counties', ['state_code'])
    # New enum member; usable once this migration's transaction commits (PG12+).
    op.execute("ALTER TYPE question_type ADD VALUE IF NOT EXISTS 'us_state_county'")


def downgrade() -> None:
    op.drop_index('ix_us_counties_state_code', table_name='us_counties')
    op.drop_table('us_counties')
    # Postgres cannot drop an enum value; 'us_state_county' remains in the type.
