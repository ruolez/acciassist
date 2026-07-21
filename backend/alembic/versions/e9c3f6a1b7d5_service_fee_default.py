"""reframe contingency fee as the AcciAssist service fee

The 33.3% default assumed an attorney contingency cut — the opposite of the
product's pitch (no attorney, patient keeps more). Rows still holding that
unedited default drop to a 10% service-fee placeholder; admins set the real
fee in Settings.

Revision ID: e9c3f6a1b7d5
Revises: d7a2e5b9f4c8
Create Date: 2026-07-20 20:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e9c3f6a1b7d5'
down_revision: str | None = 'd7a2e5b9f4c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE app_settings SET contingency_fee_pct = 10 WHERE contingency_fee_pct = 33.3"
    )


def downgrade() -> None:
    pass
