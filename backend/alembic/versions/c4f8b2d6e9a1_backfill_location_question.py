"""backfill state/county question into questionnaires lacking one

Runs as a data migration so a plain `alembic upgrade head` (the standard
update path) adds the question. Questionnaires that already collect the
state — via the composite type or the older separate 'state' question —
are left untouched.

Revision ID: c4f8b2d6e9a1
Revises: b6e1f3a9c8d2
Create Date: 2026-07-13 11:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8b2d6e9a1'
down_revision: str | None = 'b6e1f3a9c8d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PROMPT = 'Which state and county did it happen in?'
HELP_TEXT = 'Deadlines, fault rules, and typical case values depend on where it happened.'


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO questions
              (injury_type_id, slug, type, prompt, help_text, is_required,
               display_order, page_group, config)
            SELECT
              it.id, 'state_county', 'us_state_county', :prompt, :help_text, true,
              COALESCE((SELECT MIN(q.display_order) - 1 FROM questions q
                        WHERE q.injury_type_id = it.id), 0),
              NULL, '{}'::jsonb
            FROM injury_types it
            WHERE NOT EXISTS (
              SELECT 1 FROM questions q
              WHERE q.injury_type_id = it.id
                AND (q.type = 'us_state_county' OR q.slug IN ('state', 'state_county'))
            )
            """
        ).bindparams(prompt=PROMPT, help_text=HELP_TEXT)
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM questions WHERE slug = 'state_county' AND type = 'us_state_county'"
    )
