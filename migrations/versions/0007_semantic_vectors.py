"""claim embeddings for semantic search

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-08
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

DATA_TABLES = ["semantic_vectors"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE semantic_vectors (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id),
            claim_id UUID NOT NULL UNIQUE REFERENCES claims(id),
            embedding vector(1536) NOT NULL,
            model_name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX semantic_vectors_embedding_hnsw_idx ON semantic_vectors "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON semantic_vectors TO locigraph_app"
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
    op.execute("DROP TABLE IF EXISTS semantic_vectors CASCADE")
