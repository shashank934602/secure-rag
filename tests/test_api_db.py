"""The API against a real (throwaway) Postgres with real tokens and fake models (ISS-023, ISS-036).

Needs Docker:   uv run pytest -m db
"""

from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.answering.answer import NO_ANSWER, build_db_answerer
from app.auth import authenticate, issue_token
from app.config import Settings
from app.db import connect
from app.ingest import ingest_folder
from app.main import create_app
from tests.conftest import PgUrls
from tests.fakes import KeywordEmbeddings, ScriptedChatModel

pytestmark = pytest.mark.db

SECRET = "test-secret-0123456789abcdef0123456789abcdef"
EMBEDDINGS = KeywordEmbeddings(["leave", "hotel"], dimensions=1024)


def _token(pg: PgUrls, email: str) -> str:
    with psycopg.connect(pg.admin) as admin:
        user_id, tenant_id = admin.execute(
            "SELECT id, tenant_id FROM users WHERE email = %s", (email,)
        ).fetchone()
    return issue_token(str(user_id), str(tenant_id), secret=SECRET)


@pytest.fixture
def two_companies(pg: PgUrls, tmp_path: Path) -> Settings:
    """Aldermoor and Northgate each get a leave policy that answers the same question."""
    settings = Settings(
        corpus_dir=tmp_path,
        embedding_model="fake:keyword",
        database_url=pg.app,
        rerank=False,
        input_guard=False,
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
        authenticator=lambda: lambda token: authenticate(token, secret=SECRET, db=pool_conn),
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
