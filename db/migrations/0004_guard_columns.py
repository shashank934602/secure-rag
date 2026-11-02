"""Guard data on chunks, and the pii:read permission (ISS-043).

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Detected at ingest (ADR-0004: text stays raw, masking happens at query time).
    op.execute("ALTER TABLE chunks ADD COLUMN pii_types text[] NOT NULL DEFAULT '{}'")
    # The ingest injection scan's score; NULL = not scanned (ingested before Phase 5).
    op.execute("ALTER TABLE chunks ADD COLUMN injection_score real")
    op.execute(
        "UPDATE users SET permissions = array_append(permissions, 'pii:read') "
        "WHERE email = 'harriet@aldermoor.example.com'"
    )


def downgrade() -> None:
    op.execute("UPDATE users SET permissions = array_remove(permissions, 'pii:read')")
    op.execute("ALTER TABLE chunks DROP COLUMN injection_score")
    op.execute("ALTER TABLE chunks DROP COLUMN pii_types")
