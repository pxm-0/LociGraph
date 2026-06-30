"""claim extraction foundation

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-30
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

DATA_TABLES = ["claims", "concept_candidates"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE claims (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            source_id UUID NOT NULL REFERENCES sources(id),
            observation_id UUID NOT NULL REFERENCES observations(id),
            claim_text TEXT NOT NULL,
            claim_type TEXT NOT NULL,
            confidence NUMERIC NOT NULL,
            extraction_method TEXT NOT NULL,
            model_name TEXT,
            prompt_version TEXT,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE concept_candidates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            source_id UUID NOT NULL REFERENCES sources(id),
            claim_id UUID NOT NULL REFERENCES claims(id),
            candidate_name TEXT NOT NULL,
            concept_type TEXT NOT NULL,
            rationale TEXT,
            confidence NUMERIC NOT NULL,
            extraction_method TEXT NOT NULL,
            model_name TEXT,
            prompt_version TEXT,
            status TEXT NOT NULL DEFAULT 'proposed',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX claims_unique_live_text
        ON claims (user_id, observation_id, claim_text)
        WHERE status IN ('proposed', 'accepted')
        """
    )
    op.execute("CREATE INDEX claims_source_status_idx ON claims (user_id, source_id, status)")
    op.execute("CREATE INDEX claims_observation_idx ON claims (user_id, observation_id)")
    op.execute(
        "CREATE INDEX concept_candidates_source_status_idx "
        "ON concept_candidates (user_id, source_id, status)"
    )
    op.execute(
        "CREATE INDEX concept_candidates_claim_idx ON concept_candidates (user_id, claim_id)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "claims, concept_candidates TO locigraph_app"
    )
    for table in DATA_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_isolation ON {table} "
            "USING (user_id = current_setting('app.current_user_id')::uuid) "
            "WITH CHECK (user_id = current_setting('app.current_user_id')::uuid)"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS concept_candidates CASCADE")
    op.execute("DROP TABLE IF EXISTS claims CASCADE")
