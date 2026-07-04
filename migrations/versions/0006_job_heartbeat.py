"""track a running job's last heartbeat for staleness detection

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-03
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ADD COLUMN heartbeat_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS heartbeat_at")
