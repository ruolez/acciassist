"""case documents

Revision ID: f4a9c1d7e3b8
Revises: e9c3f6a1b7d5
Create Date: 2026-07-20
"""

import sqlalchemy as sa
from alembic import op

revision = "f4a9c1d7e3b8"
down_revision = "e9c3f6a1b7d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer(),
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("stored_name", sa.String(length=80), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_case_documents_case_id", "case_documents", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_documents_case_id", table_name="case_documents")
    op.drop_table("case_documents")
