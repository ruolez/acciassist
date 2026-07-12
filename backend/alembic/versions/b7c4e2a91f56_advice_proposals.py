"""advice proposals

Revision ID: b7c4e2a91f56
Revises: a3f1c9e7b2d4
Create Date: 2026-07-12 12:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'b7c4e2a91f56'
down_revision: str | None = 'a3f1c9e7b2d4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('estimate_advice', sa.Column('proposals', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('estimate_advice', 'proposals')
