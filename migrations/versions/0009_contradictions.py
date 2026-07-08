"""contradictions between claims linked to the same concept

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-09
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

DATA_TABLES = ["contradictions"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE contradictions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            concept_id UUID NOT NULL REFERENCES concepts(id),
            claim_a_id UUID NOT NULL REFERENCES claims(id),
            claim_b_id UUID NOT NULL REFERENCES claims(id),
            similarity NUMERIC NOT NULL,
            classification TEXT NOT NULL DEFAULT 'unresolved',
            rationale TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            classified_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX contradictions_unique_pair ON contradictions "
        "(user_id, claim_a_id, claim_b_id)"
    )
    op.execute(
        "CREATE INDEX contradictions_concept_idx ON contradictions (user_id, concept_id)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON contradictions TO locigraph_app"
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
    op.execute("DROP TABLE IF EXISTS contradictions CASCADE")
