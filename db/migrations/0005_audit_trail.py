"""The audit trail: request records, their sources, and hash-chained audit events (ISS-050).

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_IN_SCOPE = "tenant_id = nullif(current_setting('app.tenant_id', true), '')::uuid"
_TABLES = ("requests", "request_sources", "audit_events")


def upgrade() -> None:
    # One row per question, written when it arrives (status 'started') and finalised at the end.
    # Never the raw question or answer (Invariant 5): a keyed hash and redacted text only.
    op.execute("""
        CREATE TABLE requests (
            id                   uuid PRIMARY KEY,
            tenant_id            uuid NOT NULL REFERENCES tenants (id),
            user_id              uuid,
            query_hmac           text NOT NULL,
            query_redacted       text NOT NULL,
            answer_redacted      text,
            status               text NOT NULL DEFAULT 'started',
            model                text,
            prompt_version       text,
            judge_prompt_version text,
            latency_ms           integer,
            created_at           timestamptz NOT NULL DEFAULT now(),
            finished_at          timestamptz
        )""")
    op.execute("CREATE INDEX requests_tenant_created ON requests (tenant_id, created_at DESC)")

    # Which chunks a request used. A text reference (doc:page:index), not a foreign key, so
    # re-ingesting a document (which replaces its chunks) never erases what an answer was based on.
    op.execute("""
        CREATE TABLE request_sources (
            request_id uuid NOT NULL REFERENCES requests (id),
            tenant_id  uuid NOT NULL REFERENCES tenants (id),
            rank       integer NOT NULL,
            chunk_ref  text NOT NULL,
            score      double precision,
            PRIMARY KEY (request_id, rank)
        )""")

    # One row per decision, chained per tenant by seq / prev_hash / row_hash (app/audit/chain.py).
    op.execute("""
        CREATE TABLE audit_events (
            id         bigserial PRIMARY KEY,
            tenant_id  uuid NOT NULL REFERENCES tenants (id),
            seq        bigint NOT NULL,
            request_id uuid REFERENCES requests (id),
            actor_id   uuid,
            stage      text NOT NULL,
            decision   text NOT NULL,
            score      double precision,
            details    jsonb NOT NULL DEFAULT '{}',
            created_at timestamptz NOT NULL,
            prev_hash  text NOT NULL,
            row_hash   text NOT NULL,
            UNIQUE (tenant_id, seq)
        )""")

    # Append-only for everyone (Invariant 6): only someone able to disable triggers (a superuser)
    # could change history, and /verify would then detect it.
    op.execute("""
        CREATE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP;
        END $$""")
    op.execute(
        "CREATE TRIGGER audit_events_no_change BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only()"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only()"
    )

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING ({_IN_SCOPE}) WITH CHECK ({_IN_SCOPE})"
        )
    op.execute("GRANT SELECT, INSERT, UPDATE ON requests TO rag_app")  # UPDATE: finalise only
    op.execute("GRANT SELECT, INSERT ON request_sources, audit_events TO rag_app")
    op.execute("GRANT USAGE ON SEQUENCE audit_events_id_seq TO rag_app")

    # An auditor for Aldermoor (permission `auditor`, spec 06 D7).
    op.execute("""
        INSERT INTO users (tenant_id, email, roles, permissions)
        SELECT id, 'audrey@aldermoor.example.com', '{employee}', '{auditor}'
        FROM tenants WHERE name = 'Aldermoor'""")


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE email = 'audrey@aldermoor.example.com'")
    op.execute("DROP TABLE audit_events, request_sources, requests")
    op.execute("DROP FUNCTION audit_events_append_only()")
