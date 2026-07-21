"""admin-configurable document types

Revision ID: c7e2f9a4b6d3
Revises: b3d8e5f2a7c1
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op

revision = "c7e2f9a4b6d3"
down_revision = "b3d8e5f2a7c1"
branch_labels = None
depends_on = None

_DEFAULTS = [
    "Medical bill",
    "Medical record",
    "Photo",
    "Insurance letter",
    "Proof of income",
    "Other",
]

# The first labels shipped as slugs; convert them to display names so old
# uploads match the new type names.
_SLUG_TO_NAME = {
    "medical_bill": "Medical bill",
    "medical_record": "Medical record",
    "photo": "Photo",
    "insurance": "Insurance letter",
    "income": "Proof of income",
    "other": "Other",
}


def upgrade() -> None:
    op.alter_column(
        "case_documents",
        "label",
        type_=sa.String(length=100),
        existing_type=sa.String(length=30),
    )
    op.create_table(
        "document_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    types_table = sa.table(
        "document_types",
        sa.column("name", sa.String),
        sa.column("display_order", sa.Integer),
    )
    op.bulk_insert(
        types_table,
        [{"name": name, "display_order": i} for i, name in enumerate(_DEFAULTS)],
    )
    for old, new in _SLUG_TO_NAME.items():
        op.execute(
            sa.text("UPDATE case_documents SET label = :new WHERE label = :old").bindparams(
                new=new, old=old
            )
        )


def downgrade() -> None:
    op.drop_table("document_types")
    op.alter_column(
        "case_documents",
        "label",
        type_=sa.String(length=30),
        existing_type=sa.String(length=100),
    )
