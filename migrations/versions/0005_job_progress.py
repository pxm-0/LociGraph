"""add items_completed/items_total progress columns to jobs

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-04
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN items_completed INTEGER")
    op.execute("ALTER TABLE jobs ADD COLUMN items_total INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN items_completed")
    op.execute("ALTER TABLE jobs DROP COLUMN items_total")
