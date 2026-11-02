"""S1 (ISS-035): row-level security keeps tenants apart, even when a query forgets its WHERE.

Needs Docker:   uv run pytest -m db
"""

from collections.abc import Iterator

import psycopg
import pytest

from app.db import connect, tenant_scope
from tests.conftest import PgUrls

pytestmark = pytest.mark.db


@pytest.fixture
def two_tenants(pg: PgUrls) -> Iterator[dict[str, str]]:
    """One document + chunk per tenant, written by the admin (a superuser bypasses RLS)."""
    ids = {}
    with psycopg.connect(pg.admin, autocommit=True) as admin:
        for tenant, slug in (("Aldermoor", "leave-policy"), ("Northgate Haulage", "ng-leave")):
            (tenant_id,) = admin.execute(
                "SELECT id FROM tenants WHERE name = %s", (tenant,)
            ).fetchone()
            (doc_id,) = admin.execute(
                """INSERT INTO documents (tenant_id, slug, source, content_hash, allowed_roles,
                                          collection)
                   VALUES (%s, %s, %s, 'h', '{employee}', 'test') RETURNING id""",
                (tenant_id, slug, f"{slug}.md"),
            ).fetchone()
            admin.execute(
                """INSERT INTO chunks (document_id, tenant_id, allowed_roles, page, chunk_index,
                                       content, embedding, embedding_model, content_hash)
                   VALUES (%s, %s, '{employee}', 1, 0, %s, %s::vector, 'fake', 'h')""",
                (doc_id, tenant_id, f"{slug} text", "[" + ",".join(["0.1"] * 1024) + "]"),
            )
            ids[tenant] = str(tenant_id)
    yield ids


def test_rls_is_on_for_every_tenant_table(pg: PgUrls) -> None:
    with psycopg.connect(pg.admin) as admin:
        rows = admin.execute(
            "SELECT relname, relrowsecurity FROM pg_class "
            "WHERE relname IN ('documents', 'chunks', 'users')"
        ).fetchall()
    assert dict(rows) == {"documents": True, "chunks": True, "users": True}


def test_without_a_tenant_scope_nothing_is_visible(pg: PgUrls, two_tenants) -> None:
    # Fail closed: a code path that forgets to set the scope sees nothing, not everything.
    with connect(pg.app) as conn:
        for table in ("documents", "chunks", "users"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,), table


def test_a_query_without_where_still_sees_only_its_own_tenant(pg: PgUrls, two_tenants) -> None:
    # The Phase 4 "done when": deliberately no `WHERE tenant_id` — RLS alone keeps Northgate out.
    with connect(pg.app, autocommit=True) as conn, tenant_scope(conn, two_tenants["Aldermoor"]):
        slugs = [r[0] for r in conn.execute("SELECT slug FROM documents").fetchall()]
        chunk_text = [r[0] for r in conn.execute("SELECT content FROM chunks").fetchall()]
        emails = [r[0] for r in conn.execute("SELECT email FROM users").fetchall()]

    assert slugs == ["leave-policy"]
    assert chunk_text == ["leave-policy text"]
    assert all(email.endswith("@aldermoor.example.com") for email in emails) and emails


def test_a_tenant_cannot_write_rows_for_another_tenant(pg: PgUrls, two_tenants) -> None:
    with connect(pg.app, autocommit=True) as conn:
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege, match="row-level security"),
            tenant_scope(conn, two_tenants["Aldermoor"]),
        ):
            conn.execute(
                """INSERT INTO documents (tenant_id, slug, source, content_hash, allowed_roles,
                                          collection)
                   VALUES (%s, 'planted', 'planted.md', 'h', '{employee}', 'test')""",
                (two_tenants["Northgate Haulage"],),
            )


def test_a_tenant_cannot_change_or_delete_another_tenants_rows(pg: PgUrls, two_tenants) -> None:
    with connect(pg.app, autocommit=True) as conn, tenant_scope(conn, two_tenants["Aldermoor"]):
        changed = conn.execute(
            "UPDATE documents SET allowed_roles = '{hr}' WHERE slug = 'ng-leave'"
        )
        deleted = conn.execute("DELETE FROM chunks WHERE content = 'ng-leave text'")
    assert (changed.rowcount, deleted.rowcount) == (0, 0)


def test_the_scope_ends_with_its_transaction(pg: PgUrls, two_tenants) -> None:
    # A pooled connection must not carry one request's tenant into the next request.
    with connect(pg.app, autocommit=True) as conn:
        with tenant_scope(conn, two_tenants["Aldermoor"]):
            pass
        assert conn.execute("SELECT count(*) FROM documents").fetchone() == (0,)


def test_users_are_seeded_with_roles_and_permissions(pg: PgUrls) -> None:
    with psycopg.connect(pg.admin) as admin:
        rows = admin.execute(
            "SELECT email, roles, permissions FROM users ORDER BY email"
        ).fetchall()
    assert rows == [
        ("alice@aldermoor.example.com", ["employee"], []),
        ("harriet@aldermoor.example.com", ["employee", "hr"], ["uploader"]),
        ("ned@northgate.example.com", ["employee"], []),
    ]
