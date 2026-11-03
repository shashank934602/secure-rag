"""S3 (ISS-052): the auditor's view — open a request, search, verify; tenant-scoped; reads audited.

Needs Docker:   uv run pytest -m db
"""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.audit.recorder import AuditRecorder
from app.auth import authenticate, issue_token
from app.db import connect
from app.domain import AnswerResult, Chunk, Citation, GuardVerdict, ScoredChunk, User
from app.main import create_app
from tests.conftest import PgUrls

pytestmark = pytest.mark.db
SECRET = "test-secret-0123456789abcdef0123456789abcdef"
KEY = "test-audit-key"


def _user(pg: PgUrls, email: str) -> User:
    with psycopg.connect(pg.admin) as admin:
        uid, tid, roles, perms = admin.execute(
            "SELECT id, tenant_id, roles, permissions FROM users WHERE email = %s", (email,)
        ).fetchone()
    return User(id=str(uid), tenant_id=str(tid), email=email, roles=roles, permissions=perms)


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_token(user.id, user.tenant_id, secret=SECRET)}"}


def _record(conn, user: User, status: str = "answered") -> str:
    """One finished request, recorded the way /v1/ask records it."""
    request_id = str(uuid.uuid4())
    chunk = Chunk(id="leave:1:0", doc_id="leave", source="l.md", page=1, text="t")
    result = AnswerResult(
        status=status, answer="25 days [leave:1].", citations=[Citation(doc_id="leave", page=1)],
        retrieved=[ScoredChunk(chunk=chunk, score=0.9)], prompt_version="answer_v1",
        verdicts=[GuardVerdict(guard="input", decision="ALLOW", score=0.01, reason="classifier")],
        timings={"generate": 800.0},
    )  # fmt: skip
    recorder = AuditRecorder(conn, KEY)
    recorder.start(request_id, user, "How much leave?")
    recorder.finish(request_id, user, result, latency_ms=900, model="m")
    return request_id


@pytest.fixture
def app_client(pg: PgUrls):
    conn = connect(pg.app, autocommit=True)
    app = create_app(
        build=lambda: None,
        health_check=lambda: None,
        authenticator=lambda: lambda token: authenticate(token, secret=SECRET, db=conn),
        database=lambda: conn,
        recorder=lambda: AuditRecorder(conn, KEY),
    )
    with TestClient(app) as client:
        yield client, conn


def test_an_auditor_opens_a_request_and_sees_every_decision(pg: PgUrls, app_client) -> None:
    client, conn = app_client
    audrey, alice = (
        _user(pg, "audrey@aldermoor.example.com"),
        _user(pg, "alice@aldermoor.example.com"),
    )
    request_id = _record(conn, alice)

    body = client.get(f"/v1/audit/requests/{request_id}", headers=_bearer(audrey)).json()

    assert body["request"]["status"] == "answered"
    assert body["request"]["user_id"] == alice.id
    assert body["request"]["query_redacted"] == "How much leave?"
    assert body["sources"] == [{"rank": 1, "chunk_ref": "leave:1:0", "score": 0.9}]
    assert [(e["stage"], e["decision"]) for e in body["events"]] == [
        ("request", "START"), ("input_guard", "ALLOW"), ("retrieve", "OK"), ("finish", "ANSWERED"),
    ]  # fmt: skip


def test_reading_the_audit_is_itself_audited(pg: PgUrls, app_client) -> None:
    client, conn = app_client
    audrey = _user(pg, "audrey@aldermoor.example.com")
    request_id = _record(conn, _user(pg, "alice@aldermoor.example.com"))

    client.get(f"/v1/audit/requests/{request_id}", headers=_bearer(audrey))

    with psycopg.connect(pg.admin) as admin:
        reads = admin.execute(
            "SELECT actor_id, details FROM audit_events WHERE stage = 'audit_read'"
        ).fetchall()
    assert [(str(actor), details["request_id"]) for actor, details in reads] == [
        (audrey.id, request_id)
    ]


def test_search_filters_by_status(pg: PgUrls, app_client) -> None:
    client, conn = app_client
    alice = _user(pg, "alice@aldermoor.example.com")
    _record(conn, alice, "answered")
    refused = _record(conn, alice, "refused")

    found = client.get(
        "/v1/audit/requests", params={"status": "refused"},
        headers=_bearer(_user(pg, "audrey@aldermoor.example.com")),
    ).json()["requests"]  # fmt: skip

    assert [r["id"] for r in found] == [refused]


def test_verify_reports_a_healthy_chain_and_then_a_tampered_one(pg: PgUrls, app_client) -> None:
    client, conn = app_client
    audrey = _user(pg, "audrey@aldermoor.example.com")
    _record(conn, _user(pg, "alice@aldermoor.example.com"))

    healthy = client.get("/v1/audit/verify", headers=_bearer(audrey)).json()
    with psycopg.connect(pg.admin, autocommit=True) as admin:
        admin.execute("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_change")
        admin.execute("UPDATE audit_events SET decision = 'BLOCK' WHERE seq = 2")
        admin.execute("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_change")
    tampered = client.get("/v1/audit/verify", headers=_bearer(audrey)).json()

    assert healthy["ok"] is True and healthy["first_broken"] is None
    assert (tampered["ok"], tampered["first_broken"]) == (False, 2)


def test_only_auditors_may_look(pg: PgUrls, app_client) -> None:
    client, conn = app_client
    alice = _user(pg, "alice@aldermoor.example.com")
    request_id = _record(conn, alice)
    for url in (f"/v1/audit/requests/{request_id}", "/v1/audit/requests", "/v1/audit/verify"):
        assert client.get(url, headers=_bearer(alice)).status_code == 403, url
        assert client.get(url).status_code == 401, url


def test_an_auditor_cannot_see_another_tenants_request(pg: PgUrls, app_client) -> None:
    client, conn = app_client
    northgate_request = _record(conn, _user(pg, "ned@northgate.example.com"))
    audrey = _user(pg, "audrey@aldermoor.example.com")

    response = client.get(f"/v1/audit/requests/{northgate_request}", headers=_bearer(audrey))
    listed = client.get("/v1/audit/requests", headers=_bearer(audrey)).json()["requests"]

    assert response.status_code == 404  # RLS: it doesn't exist for Aldermoor
    assert northgate_request not in [r["id"] for r in listed]


def test_a_malformed_request_id_is_422(pg: PgUrls, app_client) -> None:
    client, _ = app_client
    audrey = _user(pg, "audrey@aldermoor.example.com")
    assert client.get("/v1/audit/requests/not-a-uuid", headers=_bearer(audrey)).status_code == 422


def test_refused_and_missing_reads_are_audited_too(pg: PgUrls, app_client) -> None:
    # Tester v0.6.0 T-4: who tried to look is evidence, not only who looked.
    client, conn = app_client
    alice, audrey = (
        _user(pg, "alice@aldermoor.example.com"),
        _user(pg, "audrey@aldermoor.example.com"),
    )
    request_id, unknown = _record(conn, alice), str(uuid.uuid4())

    assert client.get(f"/v1/audit/requests/{request_id}", headers=_bearer(alice)).status_code == 403
    assert client.get("/v1/audit/verify", headers=_bearer(alice)).status_code == 403
    assert client.get(f"/v1/audit/requests/{unknown}", headers=_bearer(audrey)).status_code == 404

    with psycopg.connect(pg.admin) as admin:
        reads = admin.execute(
            "SELECT actor_id, decision, details FROM audit_events WHERE stage = 'audit_read' "
            "ORDER BY seq"
        ).fetchall()
    assert [(str(actor), decision, details) for actor, decision, details in reads] == [
        (alice.id, "BLOCK", {"request_id": request_id, "status": 403}),
        (alice.id, "BLOCK", {"verify": None, "status": 403}),
        (audrey.id, "BLOCK", {"request_id": unknown, "status": 404}),
    ]
