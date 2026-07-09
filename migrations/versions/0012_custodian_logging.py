"""custodian logging — proposed-item workflow, notes, importance signals

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-09
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

DATA_TABLES = ["custodian_logged_items", "notes", "importance_signals"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE custodian_logged_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            session_id UUID NOT NULL REFERENCES custodian_sessions(id),
            message_id UUID REFERENCES custodian_messages(id),
            item_type TEXT NOT NULL,
            target_id UUID,
            content JSONB NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE importance_signals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            target_type TEXT NOT NULL,
            target_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX custodian_logged_items_session_idx ON custodian_logged_items "
        "(session_id, created_at)"
    )
    for table in DATA_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO locigraph_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_isolation ON {table} "
            "USING (user_id = current_setting('app.current_user_id')::uuid) "
            "WITH CHECK (user_id = current_setting('app.current_user_id')::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS custodian_logged_items CASCADE")
    op.execute("DROP TABLE IF EXISTS notes CASCADE")
    op.execute("DROP TABLE IF EXISTS importance_signals CASCADE")
