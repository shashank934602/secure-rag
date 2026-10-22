"""S2 (ISS-021): ingest the corpus into Postgres — fingerprints, transactions, idempotency.

Needs Docker:   uv run pytest -m db
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from app.config import ROOT, Settings
from app.db import connect
from app.ingest import ingest_folder, main
from tests.conftest import PgUrls
from tests.fakes import CountingEmbeddings

pytestmark = pytest.mark.db

ALL_SLUGS = sorted(p.stem for p in (ROOT / "data" / "sample").iterdir())  # the 11 documents


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A private copy of the sample corpus, so tests can edit, add, and delete files."""
    return shutil.copytree(ROOT / "data" / "sample", tmp_path / "corpus")


@pytest.fixture
def conn(pg: PgUrls) -> Iterator[psycopg.Connection]:
    with connect(pg.app, autocommit=True) as c:
        c.execute("DELETE FROM documents")
        yield c
        c.execute("DELETE FROM documents")


def _settings(corpus: Path, pg_url: str = "") -> Settings:
    return Settings(corpus_dir=corpus, embedding_model="fake:counting", database_url=pg_url)


def _chunk_count(conn: psycopg.Connection, slug: str | None = None) -> int:
    sql = "SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id"
    if slug is None:
        return conn.execute(sql).fetchone()[0]
    return conn.execute(sql + " WHERE d.slug = %s", (slug,)).fetchone()[0]


# --- first run ------------------------------------------------------------------------------


def test_first_run_adds_every_document_and_embeds_every_chunk_once(conn, corpus) -> None:
    embeddings = CountingEmbeddings()

    report = ingest_folder(conn, _settings(corpus), embeddings)

    assert sorted(report.added) == ALL_SLUGS
    assert (report.updated, report.unchanged, report.removed, report.failed) == ([], [], [], {})
    assert _chunk_count(conn) == 23
    assert len(embeddings.embedded) == 23


def test_chunks_keep_their_page_index_model_roles_and_full_size(conn, corpus) -> None:
    ingest_folder(conn, _settings(corpus), CountingEmbeddings())

    rows = conn.execute(
        """SELECT c.page, c.chunk_index, c.embedding_model, vector_dims(c.embedding),
                  c.allowed_roles, c.tenant_id = d.tenant_id
           FROM chunks c JOIN documents d ON d.id = c.document_id
           WHERE d.slug = 'vendor-contract-swiftparts' ORDER BY c.page, c.chunk_index"""
    ).fetchall()

    assert [r[0] for r in rows] == [1, 2, 3]  # the 3-page PDF: one chunk per page
    assert all(r[1:] == (0, "fake:counting", 1024, ["employee"], True) for r in rows)


# --- idempotency: running again changes nothing and costs nothing ----------------------------


def test_second_run_skips_everything_and_embeds_nothing(conn, corpus) -> None:
    ingest_folder(conn, _settings(corpus), CountingEmbeddings())
    before = conn.execute("SELECT id FROM chunks ORDER BY id").fetchall()
    embeddings = CountingEmbeddings()

    report = ingest_folder(conn, _settings(corpus), embeddings)

    assert sorted(report.unchanged) == ALL_SLUGS
    assert (report.added, report.updated, report.removed) == ([], [], [])
    assert embeddings.embedded == []  # unchanged fingerprint → no model call, no cost
    assert conn.execute("SELECT id FROM chunks ORDER BY id").fetchall() == before


# --- changes: only what changed is reprocessed ------------------------------------------------


def test_an_edited_file_is_the_only_one_reprocessed(conn, corpus) -> None:
    ingest_folder(conn, _settings(corpus), CountingEmbeddings())
    path = corpus / "annual-leave-policy.md"
    path.write_text(path.read_text() + "\n\n## 9. Volunteering\nTwo paid volunteering days.\n")
    embeddings = CountingEmbeddings()

    report = ingest_folder(conn, _settings(corpus), embeddings)

    assert report.updated == ["annual-leave-policy"]
    assert len(report.unchanged) == 10
    assert len(embeddings.embedded) == _chunk_count(conn, "annual-leave-policy")
    assert all("Aldermoor" in t or "leave" in t.lower() for t in embeddings.embedded)
    version, contents = conn.execute(
        """SELECT d.version, string_agg(c.content, ' ')
           FROM documents d JOIN chunks c ON c.document_id = d.id
           WHERE d.slug = 'annual-leave-policy' GROUP BY d.version"""
    ).fetchone()
    assert version == 2
    assert "volunteering days" in contents


def test_a_deleted_file_removes_its_document_and_chunks(conn, corpus) -> None:
    ingest_folder(conn, _settings(corpus), CountingEmbeddings())
    org_chart_chunks = _chunk_count(conn, "org-chart")
    (corpus / "org-chart.md").unlink()

    report = ingest_folder(conn, _settings(corpus), CountingEmbeddings())

    assert report.removed == ["org-chart"]
    assert _chunk_count(conn, "org-chart") == 0
    assert _chunk_count(conn) == 23 - org_chart_chunks


def test_a_new_file_is_added(conn, corpus) -> None:
    ingest_folder(conn, _settings(corpus), CountingEmbeddings())
    (corpus / "parking-policy.md").write_text("# Parking Policy\n\nStaff park in Bay C.\n")

    report = ingest_folder(conn, _settings(corpus), CountingEmbeddings())

    assert report.added == ["parking-policy"]
    assert _chunk_count(conn, "parking-policy") == 1


# --- transactions: a failure leaves the previous version intact -------------------------------


def test_a_failed_document_keeps_its_previous_version(conn, corpus) -> None:
    ingest_folder(conn, _settings(corpus), CountingEmbeddings())
    old_hash = conn.execute(
        "SELECT content_hash FROM documents WHERE slug = 'expense-policy'"
    ).fetchone()[0]
    old_chunks = _chunk_count(conn, "expense-policy")
    path = corpus / "expense-policy.md"
    path.write_text(path.read_text() + "\nNew rule.\n")

    # A wrong model returns 3 numbers instead of 1,024: the database rejects the new chunks
    # half-way through, so the whole document's transaction must roll back.
    report = ingest_folder(conn, _settings(corpus), CountingEmbeddings(dimensions=3))

    assert list(report.failed) == ["expense-policy"]
    assert len(report.unchanged) == 10  # one bad document doesn't stop the others
    new_hash = conn.execute(
        "SELECT content_hash FROM documents WHERE slug = 'expense-policy'"
    ).fetchone()[0]
    assert new_hash == old_hash
    assert _chunk_count(conn, "expense-policy") == old_chunks


# --- the command ------------------------------------------------------------------------------


def test_command_prints_the_counts(conn, corpus, pg, capsys) -> None:
    code = main([], settings=_settings(corpus, pg.app), embeddings=CountingEmbeddings())

    assert code == 0
    assert "added 11 · updated 0 · unchanged 0 · removed 0" in capsys.readouterr().out


def test_command_exits_1_when_a_document_fails(conn, corpus, pg, capsys) -> None:
    code = main([], settings=_settings(corpus, pg.app), embeddings=CountingEmbeddings(dimensions=3))

    assert code == 1
    assert "failed" in capsys.readouterr().out
