"""revisions — history of concept description changes

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-09
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

DATA_TABLES = ["revisions"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE revisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            concept_id UUID NOT NULL REFERENCES concepts(id),
            contradiction_id UUID REFERENCES contradictions(id),
            source TEXT NOT NULL,
            previous_description TEXT,
            new_description TEXT NOT NULL,
            rationale TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX revisions_concept_idx ON revisions (user_id, concept_id)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON revisions TO locigraph_app"
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
    op.execute("DROP TABLE IF EXISTS revisions CASCADE")
