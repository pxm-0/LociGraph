"""planetary_nodes — Planetarium projection cache

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-10
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

DATA_TABLES = ["planetary_nodes"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE planetary_nodes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            concept_id UUID NOT NULL REFERENCES concepts(id),
            x DOUBLE PRECISION NOT NULL,
            y DOUBLE PRECISION NOT NULL,
            z DOUBLE PRECISION NOT NULL,
            theta DOUBLE PRECISION NOT NULL,
            phi DOUBLE PRECISION NOT NULL,
            radius DOUBLE PRECISION NOT NULL,
            mass DOUBLE PRECISION NOT NULL,
            brightness DOUBLE PRECISION NOT NULL,
            color TEXT NOT NULL,
            visual_class TEXT NOT NULL,
            projection_version TEXT NOT NULL,
            projection_algorithm TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, concept_id)
        )
        """
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
    op.execute("DROP TABLE IF EXISTS planetary_nodes CASCADE")
