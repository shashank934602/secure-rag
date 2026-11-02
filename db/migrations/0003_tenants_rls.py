"""Row-level security, a second tenant, seeded users, and document collections (ISS-035).

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# A row is visible (USING) and may be written (WITH CHECK) only inside its own tenant's scope.
# With no scope set, current_setting(..., true) is '' → NULL → nothing matches: fail closed.
_IN_SCOPE = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"
_TABLES = ("documents", "chunks", "users")


def upgrade() -> None:
    # Which folder a document was ingested from, so ingesting one folder never removes another's.
    op.execute("ALTER TABLE documents ADD COLUMN collection text NOT NULL DEFAULT 'sample'")
    op.execute("ALTER TABLE documents ALTER COLUMN collection DROP DEFAULT")

    # Roles say which documents you can read; permissions say what you can do (GLOSSARY).
    op.execute("ALTER TABLE users ADD COLUMN permissions text[] NOT NULL DEFAULT '{}'")

    op.execute("UPDATE tenants SET roles = '{employee,hr}' WHERE name = 'Aldermoor'")
    op.execute("INSERT INTO tenants (name, roles) VALUES ('Northgate Haulage', '{employee}')")
    op.execute("""
        INSERT INTO users (tenant_id, email, roles, permissions)
        SELECT t.id, u.email, u.roles, u.permissions
        FROM (VALUES
            ('Aldermoor', 'alice@aldermoor.example.com', '{employee}'::text[], '{}'::text[]),
            ('Aldermoor', 'harriet@aldermoor.example.com', '{employee,hr}', '{uploader}'),
            ('Northgate Haulage', 'ned@northgate.example.com', '{employee}', '{}')
        ) AS u(tenant, email, roles, permissions)
        JOIN tenants t ON t.name = u.tenant""")

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_IN_SCOPE}) WITH CHECK ({_IN_SCOPE})"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DELETE FROM users")
    op.execute(
        "DELETE FROM documents "
        "WHERE tenant_id = (SELECT id FROM tenants WHERE name = 'Northgate Haulage')"
    )
    op.execute("DELETE FROM tenants WHERE name = 'Northgate Haulage'")
    op.execute("UPDATE tenants SET roles = '{employee}' WHERE name = 'Aldermoor'")
    op.execute("ALTER TABLE users DROP COLUMN permissions")
    op.execute("ALTER TABLE documents DROP COLUMN collection")
