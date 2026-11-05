"""The API against a real (throwaway) Postgres with real tokens and fake models (ISS-023, ISS-036).

Needs Docker:   uv run pytest -m db
"""

from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.answering.answer import NO_ANSWER, build_db_answerer
from app.audit.recorder import AuditRecorder
from app.auth import authenticate, issue_token
from app.config import Settings
from app.db import connect
from app.ingest import ingest_folder
from app.main import create_app
from tests.conftest import PgUrls
from tests.fakes import KeywordEmbeddings, ScriptedChatModel
from tests.keys import KEYS

pytestmark = pytest.mark.db

EMBEDDINGS = KeywordEmbeddings(["leave", "hotel"], dimensions=1024)


def _token(pg: PgUrls, email: str) -> str:
    with psycopg.connect(pg.admin) as admin:
        user_id, tenant_id = admin.execute(
            "SELECT id, tenant_id FROM users WHERE email = %s", (email,)
        ).fetchone()
    return issue_token(str(user_id), str(tenant_id), keys=KEYS)


@pytest.fixture
def two_companies(pg: PgUrls, tmp_path: Path) -> Settings:
    """Aldermoor and Northgate each get a leave policy that answers the same question."""
    settings = Settings(
        corpus_dir=tmp_path,
        embedding_model="fake:keyword",
        database_url=pg.app,
        rerank=False,
        input_guard=False,
        grounding_judge=False,
    )
    with connect(pg.app, autocommit=True) as conn:
        for tenant, name, text in (
            ("Aldermoor", "af-leave", "Aldermoor leave is 25 days."),
            ("Northgate Haulage", "ng-leave", "Northgate leave is 28 days. CANARY-NG-TEST"),
        ):
            folder = tmp_path / name
            folder.mkdir()
            (folder / f"{name}.md").write_text(text)
            tenant_settings = settings.model_copy(update={"tenant": tenant, "corpus_dir": folder})
            ingest_folder(conn, tenant_settings, EMBEDDINGS)
    return settings


def _client(pg: PgUrls, settings: Settings, model: ScriptedChatModel) -> TestClient:
    pool_conn = connect(pg.app, autocommit=True)
    app = create_app(
        build=lambda: build_db_answerer(settings, embeddings=EMBEDDINGS, chat_model=model),
        health_check=lambda: pool_conn.execute("SELECT 1"),
        authenticator=lambda: lambda token: authenticate(token, keys=KEYS, db=pool_conn),
        recorder=lambda: AuditRecorder(pool_conn, "test-audit-key"),
    )
    return TestClient(app)


def test_each_user_is_answered_from_their_own_company_only(pg: PgUrls, two_companies) -> None:
    model = ScriptedChatModel(responses=[NO_ANSWER, NO_ANSWER])
    with _client(pg, two_companies, model) as client:
        for email in ("alice@aldermoor.example.com", "ned@northgate.example.com"):
            response = client.post(
                "/v1/ask",
                json={"question": "How much leave do I get?"},
                headers={"Authorization": f"Bearer {_token(pg, email)}"},
            )
            assert response.status_code == 200

    alice_prompt, ned_prompt = (call[1].content for call in model.calls)
    assert "Aldermoor leave is 25 days." in alice_prompt
    assert "Northgate" not in alice_prompt and "CANARY" not in alice_prompt
    assert "Northgate leave is 28 days." in ned_prompt
    assert "Aldermoor" not in ned_prompt


def test_healthz_and_a_missing_token(pg: PgUrls, two_companies) -> None:
    with _client(pg, two_companies, ScriptedChatModel(responses=[])) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.post("/v1/ask", json={"question": "leave?"}).status_code == 401


# --- the audit trail through the API (Phase 6, ISS-051) ---------------------------------------


def _audit(pg: PgUrls, sql: str) -> list[tuple]:
    with psycopg.connect(pg.admin) as admin:
        return admin.execute(sql).fetchall()


def test_every_question_is_recorded_for_its_own_tenant(pg: PgUrls, two_companies) -> None:
    model = ScriptedChatModel(responses=["Aldermoor leave is 25 days [af-leave:1].", NO_ANSWER])
    with _client(pg, two_companies, model) as client:
        for email in ("alice@aldermoor.example.com", "ned@northgate.example.com"):
            client.post(
                "/v1/ask",
                json={"question": "How much leave do I get?"},
                headers={"Authorization": f"Bearer {_token(pg, email)}"},
            )

    requests = _audit(
        pg,
        "SELECT t.name, r.status, r.query_redacted, r.answer_redacted IS NOT NULL "
        "FROM requests r JOIN tenants t ON t.id = r.tenant_id ORDER BY t.name",
    )
    assert requests == [
        ("Aldermoor", "answered", "How much leave do I get?", True),
        ("Northgate Haulage", "no_answer", "How much leave do I get?", True),
    ]
    stages = _audit(
        pg,
        "SELECT e.stage, e.decision FROM audit_events e JOIN tenants t ON t.id = e.tenant_id "
        "WHERE t.name = 'Aldermoor' ORDER BY e.seq",
    )
    assert stages[0] == ("request", "START") and stages[-1] == ("finish", "ANSWERED")
    assert ("retrieve", "OK") in stages and ("output_checks", "PASS") in stages
    sources = _audit(
        pg,
        "SELECT chunk_ref FROM request_sources r JOIN tenants t ON t.id = r.tenant_id "
        "WHERE t.name = 'Aldermoor'",
    )
    assert sources == [("af-leave:1:0",)]


def test_if_the_audit_cannot_be_written_the_answer_is_withheld(pg: PgUrls, two_companies) -> None:
    class BrokenRecorder:
        def start(self, *args, **kwargs) -> None:
            raise ConnectionError("audit database unreachable")

    pool_conn = connect(pg.app, autocommit=True)
    model = ScriptedChatModel(responses=["never used"])
    app = create_app(
        build=lambda: build_db_answerer(two_companies, embeddings=EMBEDDINGS, chat_model=model),
        health_check=lambda: None,
        authenticator=lambda: lambda token: authenticate(token, keys=KEYS, db=pool_conn),
        recorder=BrokenRecorder,
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/ask",
            json={"question": "How much leave do I get?"},
            headers={"Authorization": f"Bearer {_token(pg, 'alice@aldermoor.example.com')}"},
        )
    assert response.status_code == 503
    assert model.calls == []  # nothing ran: no audit, no answer
