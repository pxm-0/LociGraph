"""allow re-uploading a checksum after its source was purged

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-03
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sources DROP CONSTRAINT sources_user_id_checksum_sha256_key")
    op.execute(
        "CREATE UNIQUE INDEX sources_user_id_checksum_sha256_key "
        "ON sources (user_id, checksum_sha256) WHERE import_status != 'PURGED'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sources_user_id_checksum_sha256_key")
    op.execute(
        "ALTER TABLE sources ADD CONSTRAINT sources_user_id_checksum_sha256_key "
        "UNIQUE (user_id, checksum_sha256)"
    )
