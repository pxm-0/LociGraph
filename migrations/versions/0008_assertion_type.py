"""reality/perception separation — assertion_type on claims

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-08
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE claims ADD COLUMN assertion_type TEXT")
    op.execute(
        """
        UPDATE claims SET
            assertion_type = CASE claim_type
                WHEN 'fact' THEN 'reality'
                WHEN 'event' THEN 'reality'
                WHEN 'relationship' THEN 'reality'
                WHEN 'decision' THEN 'reality'
                WHEN 'task' THEN 'reality'
                WHEN 'emotion' THEN 'perception'
                WHEN 'preference' THEN 'perception'
                WHEN 'belief' THEN 'interpretation'
                WHEN 'interpretation' THEN 'interpretation'
                WHEN 'definition' THEN 'interpretation'
            END,
            metadata = metadata || '{"assertion_type_source": "backfill_deterministic_v1"}'::jsonb
        """
    )
    op.execute("ALTER TABLE claims ALTER COLUMN assertion_type SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE claims DROP COLUMN assertion_type")
