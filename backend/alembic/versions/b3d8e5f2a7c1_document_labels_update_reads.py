"""document labels + update read state

Revision ID: b3d8e5f2a7c1
Revises: f4a9c1d7e3b8
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op

revision = "b3d8e5f2a7c1"
down_revision = "f4a9c1d7e3b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "case_documents", sa.Column("label", sa.String(length=30), nullable=True)
    )
    op.add_column(
        "case_updates", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("case_updates", "read_at")
    op.drop_column("case_documents", "label")
