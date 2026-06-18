"""initial schema with two-role RLS

Revision ID: 0001
Revises:
Create Date: 2026-06-19
"""
import os

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DATA_TABLES = ["sources", "fragments", "observations", "jobs"]


def upgrade() -> None:
    app_password = os.environ["APP_DB_PASSWORD"]

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sources (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            source_type TEXT NOT NULL,
            original_filename TEXT,
            original_mime_type TEXT,
            checksum_sha256 TEXT NOT NULL,
            file_size_bytes BIGINT,
            raw_storage_path TEXT,
            import_status TEXT NOT NULL DEFAULT 'PENDING',
            retention_policy TEXT NOT NULL DEFAULT 'standard',
            imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            verified_at TIMESTAMPTZ,
            purged_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}',
            UNIQUE (user_id, checksum_sha256)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE fragments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            source_id UUID NOT NULL REFERENCES sources(id),
            raw_index INTEGER,
            raw_payload JSONB,
            extracted_text TEXT,
            timestamp TIMESTAMPTZ,
            author TEXT,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE observations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            source_id UUID REFERENCES sources(id),
            fragment_id UUID REFERENCES fragments(id),
            observed_at TIMESTAMPTZ,
            speaker TEXT,
            content TEXT NOT NULL,
            context_before TEXT,
            context_after TEXT,
            confidence NUMERIC NOT NULL DEFAULT 1.0,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 5,
            payload JSONB NOT NULL DEFAULT '{}',
            result JSONB,
            error TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id),
            actor_type TEXT NOT NULL,
            actor_id TEXT,
            action TEXT NOT NULL,
            target_ref_type TEXT NOT NULL,
            target_ref_id UUID NOT NULL,
            before_state JSONB,
            after_state JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
        """
    )

    # Non-owner application role.
    op.execute(
        f"CREATE ROLE locigraph_app LOGIN PASSWORD '{app_password}'"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "sources, fragments, observations, jobs TO locigraph_app"
    )
    op.execute("GRANT SELECT, INSERT ON audit_logs TO locigraph_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON users TO locigraph_app")
    op.execute(
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO locigraph_app"
    )

    # Enable + FORCE RLS and add USING/WITH CHECK policies.
    for table in DATA_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_isolation ON {table} "
            "USING (user_id = current_setting('app.current_user_id')::uuid) "
            "WITH CHECK (user_id = current_setting('app.current_user_id')::uuid)"
        )


def downgrade() -> None:
    for table in ["audit_logs", "jobs", "observations", "fragments", "sources", "users"]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP ROLE IF EXISTS locigraph_app")
