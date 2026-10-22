"""Initial schema: tenants, users, documents, chunks; seed tenant; the rag_app role (ISS-020).

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import context, op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE tenants (
            id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name  text NOT NULL UNIQUE,
            roles text[] NOT NULL DEFAULT '{}'
        )""")

    op.execute("""
        CREATE TABLE users (
            id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants (id),
            email     text NOT NULL,
            roles     text[] NOT NULL DEFAULT '{}',
            UNIQUE (tenant_id, email)
        )""")

    # slug = the doc id in citations, unique per tenant (spec 01 D2).
    op.execute("""
        CREATE TABLE documents (
            id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     uuid NOT NULL REFERENCES tenants (id),
            slug          text NOT NULL,
            source        text NOT NULL,
            content_hash  text NOT NULL,
            allowed_roles text[] NOT NULL,
            version       int NOT NULL DEFAULT 1,
            status        text NOT NULL DEFAULT 'active',
            ingested_at   timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, slug)
        )""")

    # tenant_id and allowed_roles are copied from the document so search can filter on the
    # chunk alone (ADR-0002). vector(1024) matches mistral-embed (ADR-0005).
    op.execute("""
        CREATE TABLE chunks (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id     uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            tenant_id       uuid NOT NULL REFERENCES tenants (id),
            allowed_roles   text[] NOT NULL,
            page            int NOT NULL CHECK (page >= 1),
            chunk_index     int NOT NULL CHECK (chunk_index >= 0),
            content         text NOT NULL,
            embedding       vector(1024) NOT NULL,
            embedding_model text NOT NULL,
            content_hash    text NOT NULL,
            is_active       boolean NOT NULL DEFAULT true,
            UNIQUE (document_id, page, chunk_index)
        )""")

    # HNSW: an approximate nearest-neighbour index, so search doesn't compare every row.
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX chunks_tenant_active ON chunks (tenant_id, is_active)")

    op.execute("INSERT INTO tenants (name, roles) VALUES ('Aldermoor', '{employee}')")

    # The app's role: may read and write rows, may not change the schema, and is not a
    # superuser (superusers bypass row-level security). The password is passed as a bound
    # value and quoted by Postgres (%L), never pasted into the SQL text.
    op.execute(
        sa.text("SELECT set_config('rag.app_password', :password, true)").bindparams(
            password=context.config.attributes["rag_app_password"]
        )
    )
    op.execute("""
        DO $$
        DECLARE
            password text := current_setting('rag.app_password');
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rag_app') THEN
                EXECUTE format('CREATE ROLE rag_app LOGIN PASSWORD %L', password);
            ELSE
                EXECUTE format('ALTER ROLE rag_app LOGIN PASSWORD %L', password);
            END IF;
        END $$""")
    op.execute("ALTER ROLE rag_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE")
    op.execute("GRANT USAGE ON SCHEMA public TO rag_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON tenants, users, documents, chunks TO rag_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE chunks, documents, users, tenants")
    op.execute("REVOKE USAGE ON SCHEMA public FROM rag_app")
    op.execute("DROP ROLE IF EXISTS rag_app")
