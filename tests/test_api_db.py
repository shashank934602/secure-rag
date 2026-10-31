"""S4 (ISS-023): the API against a real (throwaway) Postgres, with fake models.

Needs Docker:   uv run pytest -m db
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.answering.answer import build_db_answerer
from app.config import Settings
from app.db import connect
from app.ingest import ingest_folder
from app.main import create_app
from tests.conftest import PgUrls
from tests.fakes import CountingEmbeddings, ScriptedChatModel

pytestmark = pytest.mark.db


def test_ask_and_healthz_end_to_end(pg: PgUrls, tmp_path: Path) -> None:
    (tmp_path / "leave-policy.md").write_text("Annual leave is 25 days.")
    settings = Settings(
        corpus_dir=tmp_path, embedding_model="fake:counting", database_url=pg.app, rerank=False
    )
    with connect(pg.app, autocommit=True) as conn:
        conn.execute("DELETE FROM documents")
        ingest_folder(conn, settings, CountingEmbeddings())

        def build():
            return build_db_answerer(
                settings,
                embeddings=CountingEmbeddings(),
                chat_model=ScriptedChatModel(responses=["25 days [leave-policy:1]."]),
            )

        def health_check() -> None:
            with connect(pg.app) as c:
                c.execute("SELECT 1")

        with TestClient(create_app(build=build, health_check=health_check)) as client:
            health = client.get("/healthz")
            answer = client.post("/v1/ask", json={"question": "How much leave?"})

        conn.execute("DELETE FROM documents")

    assert health.json() == {"status": "ok"}
    assert answer.json()["citations"] == [
        {"doc_id": "leave-policy", "page": 1, "source": "leave-policy.md"}
    ]
