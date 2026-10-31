"""S3 (ISS-022): the answerer reading from Postgres, end to end with fake models.

Needs Docker:   uv run pytest -m db
"""

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from app.answering.answer import build_db_answerer
from app.config import Settings
from app.db import connect
from app.ingest import ingest_folder
from tests.conftest import PgUrls
from tests.fakes import CountingEmbeddings, ScriptedChatModel

pytestmark = pytest.mark.db

QUESTION = "How much leave do I get?"


@pytest.fixture
def settings(pg: PgUrls, tmp_path: Path) -> Iterator[Settings]:
    (tmp_path / "leave-policy.md").write_text("Annual leave is 25 days.")
    (tmp_path / "expense-policy.md").write_text("Hotel limit is 190 pounds.")
    settings = Settings(
        corpus_dir=tmp_path, embedding_model="fake:counting", database_url=pg.app, rerank=False
    )
    with connect(pg.app, autocommit=True) as conn:
        conn.execute("DELETE FROM documents")
        ingest_folder(conn, settings, CountingEmbeddings())
        yield settings
        conn.execute("DELETE FROM documents")


def test_answers_from_the_database(settings: Settings) -> None:
    answerer = build_db_answerer(
        settings,
        embeddings=CountingEmbeddings(),
        chat_model=ScriptedChatModel(responses=["25 days [leave-policy:1]."]),
    )

    result = answerer.answer(QUESTION)

    assert result.status == "answered"
    assert {r.chunk.doc_id for r in result.retrieved} == {"leave-policy", "expense-policy"}


def test_only_the_question_is_embedded(settings: Settings) -> None:
    # The chunks' numbers are already stored, so a question costs one embedding, not one per chunk.
    embeddings = CountingEmbeddings()
    answerer = build_db_answerer(
        settings,
        embeddings=embeddings,
        chat_model=ScriptedChatModel(responses=["25 days [leave-policy:1]."]),
    )

    answerer.answer(QUESTION)

    assert embeddings.embedded == [QUESTION]


def test_needs_a_database_url(settings: Settings) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_db_answerer(settings.model_copy(update={"database_url": ""}))


def test_recovers_after_the_database_drops_its_connections(settings: Settings, pg: PgUrls) -> None:
    # A database restart kills every open connection. The answerer must get a fresh one on the
    # next question instead of failing forever (found by stopping the dev database, ISS-027).
    answerer = build_db_answerer(
        settings,
        embeddings=CountingEmbeddings(),
        chat_model=ScriptedChatModel(responses=["25 days [leave-policy:1]."] * 2),
    )
    answerer.answer(QUESTION)
    with psycopg.connect(pg.admin, autocommit=True) as admin:
        admin.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE application_name = 'rag-answerer'"
        )

    assert answerer.answer(QUESTION).status == "answered"
