"""S3 (ISS-037): changing a document's audience — permission, tenant, roles, one transaction.

Needs Docker:   uv run pytest -m db
"""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.audit.recorder import AuditRecorder
from app.auth import authenticate, issue_token
from app.config import Settings
from app.db import connect
from app.documents import AclError, change_acl
from app.domain import AccessScope, User
from app.ingest import ingest_folder
from app.main import create_app
from app.retrieval.pg_search import PgRetriever
from tests.conftest import PgUrls, act_as
from tests.fakes import KeywordEmbeddings
from tests.keys import KEYS

pytestmark = pytest.mark.db

EMBEDDINGS = KeywordEmbeddings(["leave", "pay"], dimensions=1024)


def _user(pg: PgUrls, email: str) -> User:
    with psycopg.connect(pg.admin) as admin:
        user_id, tenant_id = admin.execute(
            "SELECT id, tenant_id FROM users WHERE email = %s", (email,)
        ).fetchone()
    with connect(pg.app, autocommit=True) as conn:
        return authenticate(issue_token(user_id, tenant_id, keys=KEYS), keys=KEYS, db=conn)


@pytest.fixture
def conn(pg: PgUrls, tmp_path: Path) -> Iterator[psycopg.Connection]:
    """Aldermoor's leave policy (2 chunks, employee) and Northgate's (1 chunk)."""
    with connect(pg.app, autocommit=True) as c:
        for tenant, name, text in (
            ("Aldermoor", "leave-policy", "Leave is 25 days.\n\n" + "More leave rules. " * 400),
            ("Northgate Haulage", "ng-leave", "Northgate leave is 28 days."),
        ):
            folder = tmp_path / name
            folder.mkdir()
            (folder / f"{name}.md").write_text(text)
            settings = Settings(corpus_dir=folder, embedding_model="fake", tenant=tenant)
            ingest_folder(c, settings, EMBEDDINGS)
        act_as(c)
        yield c


def _roles(conn: psycopg.Connection, slug: str) -> tuple[list[str], set[tuple[str, ...]]]:
    doc = conn.execute("SELECT allowed_roles FROM documents WHERE slug = %s", (slug,)).fetchone()
    chunks = conn.execute(
        "SELECT DISTINCT c.allowed_roles FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.slug = %s",
        (slug,),
    ).fetchall()
    return doc[0], {tuple(r[0]) for r in chunks}


def test_document_and_all_its_chunks_change_together(pg, conn) -> None:
    chunks = conn.execute(
        "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id "
        "WHERE d.slug = 'leave-policy'"
    ).fetchone()[0]

    result = change_acl(conn, _user(pg, "harriet@aldermoor.example.com"), "leave-policy", ["hr"])

    assert chunks > 1  # a multi-chunk document, so "all its chunks" means something
    assert result == {"doc_id": "leave-policy", "allowed_roles": ["hr"], "chunks_updated": chunks}
    assert _roles(conn, "leave-policy") == (["hr"], {("hr",)})


def test_the_change_applies_to_search_at_once(pg, conn) -> None:
    retriever = PgRetriever(conn, EMBEDDINGS, tenant="Aldermoor", roles=["employee"])
    assert retriever.search("leave", k=5)  # employees see it now

    change_acl(conn, _user(pg, "harriet@aldermoor.example.com"), "leave-policy", ["hr"])

    assert retriever.search("leave", k=5) == []  # a removed role retrieves nothing
    hr = AccessScope(tenant_id=retriever.default_scope.tenant_id, roles=["hr"])
    assert retriever.search("leave", k=5, scope=hr)


def test_without_the_uploader_permission_it_is_forbidden(pg, conn) -> None:
    with pytest.raises(AclError) as error:
        change_acl(conn, _user(pg, "alice@aldermoor.example.com"), "leave-policy", ["hr"])
    assert error.value.status == 403
    assert _roles(conn, "leave-policy") == (["employee"], {("employee",)})


def test_another_tenants_document_is_not_found(pg, conn) -> None:
    # RLS hides it, so the answer is 404: it doesn't even confirm the document exists.
    with pytest.raises(AclError) as error:
        change_acl(conn, _user(pg, "harriet@aldermoor.example.com"), "ng-leave", ["hr"])
    assert error.value.status == 404


@pytest.mark.parametrize("roles", [["finance"], ["hr", "board"]])
def test_roles_must_belong_to_the_tenant(pg, conn, roles) -> None:
    with pytest.raises(AclError) as error:
        change_acl(conn, _user(pg, "harriet@aldermoor.example.com"), "leave-policy", roles)
    assert error.value.status == 422


def test_a_failure_halfway_changes_nothing(pg, conn) -> None:
    # Make the chunk update fail after the document row has already been updated.
    with psycopg.connect(pg.admin, autocommit=True) as admin:
        admin.execute("""
            CREATE FUNCTION refuse() RETURNS trigger LANGUAGE plpgsql AS
            $$ BEGIN RAISE EXCEPTION 'chunk update refused'; END $$;
            CREATE TRIGGER refuse_chunk_update BEFORE UPDATE ON chunks
            FOR EACH ROW EXECUTE FUNCTION refuse();""")
    try:
        with pytest.raises(psycopg.errors.RaiseException):
            change_acl(conn, _user(pg, "harriet@aldermoor.example.com"), "leave-policy", ["hr"])
    finally:
        with psycopg.connect(pg.admin, autocommit=True) as admin:
            admin.execute("DROP TRIGGER refuse_chunk_update ON chunks; DROP FUNCTION refuse();")

    # Invariant 2: the document and its chunks never disagree.
    assert _roles(conn, "leave-policy") == (["employee"], {("employee",)})


# --- the endpoint --------------------------------------------------------------------------------


def _client(pg: PgUrls, conn: psycopg.Connection) -> TestClient:
    app = create_app(
        build=lambda: None,
        health_check=lambda: None,
        authenticator=lambda: lambda token: authenticate(token, keys=KEYS, db=conn),
        database=lambda: conn,
        recorder=lambda: AuditRecorder(conn, "test-audit-key"),
    )
    return TestClient(app)


def _bearer(pg: PgUrls, email: str) -> dict[str, str]:
    user = _user(pg, email)
    return {"Authorization": f"Bearer {issue_token(user.id, user.tenant_id, keys=KEYS)}"}


def test_patch_acl_endpoint(pg, conn) -> None:
    harriet, alice = (
        _bearer(pg, "harriet@aldermoor.example.com"),
        _bearer(pg, "alice@aldermoor.example.com"),
    )
    with _client(pg, conn) as client:
        url = "/v1/documents/leave-policy/acl"
        ok = client.patch(url, json={"allowed_roles": ["hr"]}, headers=harriet)
        forbidden = client.patch(url, json={"allowed_roles": ["hr"]}, headers=alice)
        not_found = client.patch(
            "/v1/documents/ng-leave/acl", json={"allowed_roles": ["hr"]}, headers=harriet
        )
        bad_role = client.patch(url, json={"allowed_roles": ["finance"]}, headers=harriet)
        empty = client.patch(url, json={"allowed_roles": []}, headers=harriet)
        anonymous = client.patch(url, json={"allowed_roles": ["hr"]})

    assert ok.status_code == 200 and ok.json()["allowed_roles"] == ["hr"]
    assert forbidden.status_code == 403
    assert not_found.status_code == 404
    assert bad_role.status_code == 422 and empty.status_code == 422
    assert anonymous.status_code == 401


# --- access changes are audited atomically (Phase 6, ISS-051) ---------------------------------


def test_an_acl_change_and_a_refused_attempt_are_both_audited(pg, conn) -> None:
    harriet, alice = (_bearer(pg, "harriet@aldermoor.example.com"),
                      _bearer(pg, "alice@aldermoor.example.com"))  # fmt: skip
    with _client(pg, conn) as client:
        client.patch(
            "/v1/documents/leave-policy/acl", json={"allowed_roles": ["hr"]}, headers=harriet
        )
        client.patch(
            "/v1/documents/leave-policy/acl", json={"allowed_roles": ["hr"]}, headers=alice
        )

    with psycopg.connect(pg.admin) as admin:
        rows = admin.execute(
            "SELECT decision, details FROM audit_events WHERE stage = 'acl_change' ORDER BY seq"
        ).fetchall()
    assert rows[0] == ("ALLOW", {"doc_id": "leave-policy", "from": ["employee"], "to": ["hr"],
                                  "chunks_updated": rows[0][1]["chunks_updated"]})  # fmt: skip
    assert rows[1][0] == "BLOCK" and rows[1][1]["status"] == 403


def test_if_the_audit_fails_the_acl_change_is_rolled_back(pg, conn) -> None:
    def broken_audit(audit_conn, change) -> None:
        raise ConnectionError("audit unavailable")

    with pytest.raises(ConnectionError):
        change_acl(conn, _user(pg, "harriet@aldermoor.example.com"), "leave-policy", ["hr"],
                   audit=broken_audit)  # fmt: skip

    assert _roles(conn, "leave-policy") == (["employee"], {("employee",)})  # unchanged
