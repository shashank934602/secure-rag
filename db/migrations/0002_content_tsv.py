"""Keyword search: a generated full-text column on chunks, with a GIN index (ISS-030).

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # GENERATED ... STORED: Postgres computes it from `content` on every insert or update, and
    # fills it for existing rows now, so nothing is re-embedded and ingest needs no change.
    op.execute("""
        ALTER TABLE chunks
        ADD COLUMN content_tsv tsvector
            GENERATED ALWAYS AS (to_tsvector('english', content)) STORED""")
    op.execute("CREATE INDEX chunks_content_tsv_gin ON chunks USING gin (content_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX chunks_content_tsv_gin")
    op.execute("ALTER TABLE chunks DROP COLUMN content_tsv")
