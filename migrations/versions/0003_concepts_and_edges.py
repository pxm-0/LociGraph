"""canonical concepts and claim-concept graph edges

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-02
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DATA_TABLES = ["concepts", "claim_concept_edges"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE concepts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            concept_name TEXT NOT NULL,
            concept_type TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE claim_concept_edges (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            claim_id UUID NOT NULL REFERENCES claims(id),
            concept_id UUID NOT NULL REFERENCES concepts(id),
            concept_candidate_id UUID NOT NULL REFERENCES concept_candidates(id),
            confidence NUMERIC NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX concepts_unique_name_per_type "
        "ON concepts (user_id, concept_type, lower(concept_name))"
    )
    op.execute(
        "CREATE UNIQUE INDEX claim_concept_edges_unique_edge "
        "ON claim_concept_edges (user_id, claim_id, concept_id)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "concepts, claim_concept_edges TO locigraph_app"
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
    op.execute("DROP TABLE IF EXISTS claim_concept_edges CASCADE")
    op.execute("DROP TABLE IF EXISTS concepts CASCADE")
