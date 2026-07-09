"""custodian — chat sessions and messages

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-09
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

DATA_TABLES = ["custodian_sessions", "custodian_messages"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE custodian_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            title TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            ended_at TIMESTAMPTZ,
            model TEXT NOT NULL,
            provider TEXT NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE custodian_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID NOT NULL REFERENCES custodian_sessions(id),
            user_id UUID NOT NULL REFERENCES users(id),
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            tool_name TEXT,
            tool_input TEXT,
            tool_output TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX custodian_sessions_user_idx ON custodian_sessions (user_id, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX custodian_messages_session_idx ON custodian_messages (session_id, created_at)"
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
    op.execute("DROP TABLE IF EXISTS custodian_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS custodian_sessions CASCADE")
