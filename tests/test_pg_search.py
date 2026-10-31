"""S3 (ISS-022) ✍️ exercise: vector search in Postgres. Make these pass by writing `_SEARCH_SQL`.

Run only these:   uv run pytest -m db tests/test_pg_search.py -v

The corpus is three tiny documents and a keyword "embedding model", so the right answer is obvious:
a question about leave must find the leave policy first.
"""

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import psycopg
import pytest

from app.config import Settings
from app.db import connect
from app.ingest import ingest_folder
from app.ingestion.chunking import chunk_pages
from app.ingestion.loaders import load_pages
from app.retrieval.pg_search import _SEARCH_SQL, PgRetriever
from app.retrieval.search import ChunkIndex
from tests.conftest import PgUrls
from tests.fakes import KeywordEmbeddings

pytestmark = pytest.mark.db

VOCAB = ["leave", "holiday", "expense", "hotel", "laptop", "password"]
EMBEDDINGS = KeywordEmbeddings(VOCAB, dimensions=1024)
DOCS = {
    "leave-policy.md": "Annual leave is 25 days. Book holiday leave early.",
    "expense-policy.md": "Hotel expense limit is 190 pounds per night.",
    "it-policy.md": "Laptop password must be 14 characters.",
}


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    for name, text in DOCS.items():
        (tmp_path / name).write_text(text)
    return tmp_path


@pytest.fixture
def conn(pg: PgUrls, corpus: Path) -> Iterator[psycopg.Connection]:
    """rag_app connection over a database holding exactly the three documents above."""
    with connect(pg.app, autocommit=True) as c:
        c.execute("DELETE FROM documents")
        ingest_folder(c, Settings(corpus_dir=corpus, embedding_model="fake:keyword"), EMBEDDINGS)
        yield c
        c.execute("DELETE FROM documents")
        c.execute("DELETE FROM tenants WHERE name <> 'Aldermoor'")


def _retriever(
    conn: psycopg.Connection, roles: list[str] | None = None, mode: str = "dense"
) -> PgRetriever:
    return PgRetriever(conn, EMBEDDINGS, tenant="Aldermoor", roles=roles or ["employee"], mode=mode)


def _doc_ids(results) -> list[str]:
    return [r.chunk.doc_id for r in results]


# --- rule 2: closest first, at most k -----------------------------------------------------------


def test_the_most_similar_chunk_comes_first(conn) -> None:
    results = _retriever(conn).search("How much holiday leave do I get?", k=3)
    assert _doc_ids(results)[0] == "leave-policy"


def test_returns_at_most_k_chunks(conn) -> None:
    assert len(_retriever(conn).search("hotel", k=2)) == 2
    assert len(_retriever(conn).search("hotel", k=10)) == 3  # only 3 chunks exist


def test_results_are_ordered_best_first(conn) -> None:
    scores = [r.score for r in _retriever(conn).search("laptop password", k=3)]
    assert scores == sorted(scores, reverse=True)


# --- rule 3: score is similarity (1 = same meaning), not distance (0 = same) --------------------


def test_score_is_cosine_similarity_not_distance(conn) -> None:
    # Same keywords as the expense chunk → same direction → similarity 1 (distance would be 0).
    best = _retriever(conn).search("hotel expense", k=1)[0]
    assert best.chunk.doc_id == "expense-policy"
    assert best.score == pytest.approx(1.0, abs=1e-6)


# --- the chunk is rebuilt correctly from the row --------------------------------------------------


def test_chunk_has_its_id_doc_id_source_page_and_text(conn) -> None:
    chunk = _retriever(conn).search("leave", k=1)[0].chunk
    assert chunk.id == "leave-policy:1:0"
    assert (chunk.doc_id, chunk.source, chunk.page) == ("leave-policy", "leave-policy.md", 1)
    assert chunk.text == DOCS["leave-policy.md"]


# --- same answers as the in-memory search (spec 02 D4) -------------------------------------------


@pytest.mark.parametrize("question", ["holiday leave", "hotel expense", "laptop password"])
def test_same_results_as_the_in_memory_search(conn, corpus, question) -> None:
    chunks = chunk_pages(
        load_pages(corpus), chunk_size=400, chunk_overlap=50, encoding_name="cl100k_base"
    )
    in_memory = ChunkIndex(chunks, EMBEDDINGS).search(question, k=3)
    in_postgres = _retriever(conn).search(question, k=3)

    assert in_postgres[0].chunk.id == in_memory[0].chunk.id
    assert {(r.chunk.id, round(r.score, 6)) for r in in_postgres} == {
        (r.chunk.id, round(r.score, 6)) for r in in_memory
    }


# --- rule 1: only this tenant's, active, role-allowed chunks -------------------------------------


def test_inactive_chunks_are_never_returned(conn) -> None:
    conn.execute(
        """UPDATE chunks SET is_active = false
           WHERE document_id = (SELECT id FROM documents WHERE slug = 'leave-policy')"""
    )
    assert "leave-policy" not in _doc_ids(_retriever(conn).search("holiday leave", k=3))


def test_another_tenants_chunks_are_never_returned(conn) -> None:
    # A rival company with a document that matches the question perfectly.
    (rival,) = conn.execute(
        "INSERT INTO tenants (name, roles) VALUES ('Rival Ltd', '{employee}') RETURNING id"
    ).fetchone()
    (doc,) = conn.execute(
        """INSERT INTO documents (tenant_id, slug, source, content_hash, allowed_roles)
           VALUES (%s, 'rival-leave', 'rival-leave.md', 'h', '{employee}') RETURNING id""",
        (rival,),
    ).fetchone()
    conn.execute(
        """INSERT INTO chunks (document_id, tenant_id, allowed_roles, page, chunk_index, content,
                               embedding, embedding_model, content_hash)
           VALUES (%s, %s, '{employee}', 1, 0, 'Rival leave holiday', %s, 'fake', 'h')""",
        (doc, rival, np.array(EMBEDDINGS.embed_query("leave holiday"))),
    )

    assert "rival-leave" not in _doc_ids(_retriever(conn).search("leave holiday", k=10))


def test_chunks_for_other_roles_are_never_returned(conn) -> None:
    conn.execute(
        """UPDATE chunks SET allowed_roles = '{hr}'
           WHERE document_id = (SELECT id FROM documents WHERE slug = 'leave-policy')"""
    )
    assert "leave-policy" not in _doc_ids(_retriever(conn, ["employee"]).search("leave", k=3))
    assert "leave-policy" in _doc_ids(_retriever(conn, ["hr"]).search("leave", k=3))


# --- rule 4: the HNSW index can be used --------------------------------------------------------


def test_the_query_can_use_the_hnsw_index(conn) -> None:
    # With 3 rows Postgres would just read them all and sort them. Forbid both, so the only way
    # to return "closest first" is to walk the HNSW index, which is possible only if the query
    # orders by the distance `<=>` itself (ascending), not by a score computed from it.
    with conn.transaction():
        conn.execute("SET LOCAL enable_seqscan = off")
        conn.execute("SET LOCAL enable_sort = off")
        plan = conn.execute(
            "EXPLAIN " + _SEARCH_SQL,
            {
                "embedding": np.array(EMBEDDINGS.embed_query("leave")),
                "tenant_id": conn.execute("SELECT id FROM tenants").fetchone()[0],
                "roles": ["employee"],
                "k": 3,
            },
        ).fetchall()
    assert "chunks_embedding_hnsw" in "\n".join(row[0] for row in plan)


# --- edges ------------------------------------------------------------------------------------


def test_an_empty_database_returns_nothing(conn) -> None:
    conn.execute("DELETE FROM documents")
    assert _retriever(conn).search("leave", k=5) == []


def test_an_unknown_tenant_is_an_error(conn) -> None:
    with pytest.raises(ValueError, match="not found"):
        PgRetriever(conn, EMBEDDINGS, tenant="Nobody Ltd", roles=["employee"])


# --- keyword and hybrid search (Phase 3, ISS-030) ---------------------------------------------


def test_keyword_search_finds_the_chunk_with_the_exact_word(conn) -> None:
    results = _retriever(conn, mode="keyword").search("What are the password rules?", k=3)
    assert _doc_ids(results)[0] == "it-policy"


def test_keyword_search_returns_only_chunks_that_contain_a_word(conn) -> None:
    # Only the expense chunk mentions a hotel; the others don't match at all.
    assert _doc_ids(_retriever(conn, mode="keyword").search("hotel", k=10)) == ["expense-policy"]


def test_keyword_search_with_no_usable_words_returns_nothing(conn) -> None:
    assert _retriever(conn, mode="keyword").search("?!", k=5) == []


def test_keyword_search_ignores_punctuation_and_operators(conn) -> None:
    # Quotes, minus signs, and "or" must not break or change the query.
    results = _retriever(conn, mode="keyword").search('"hotel" -limit OR or (password)', k=5)
    assert set(_doc_ids(results)) == {"expense-policy", "it-policy"}


def test_hybrid_search_combines_both_lists(conn) -> None:
    results = _retriever(conn, mode="hybrid").search("hotel expense", k=3)
    assert _doc_ids(results)[0] == "expense-policy"
    assert len(results) == 3  # dense contributes chunks keyword search didn't match


@pytest.mark.parametrize("mode", ["keyword", "hybrid"])
def test_every_mode_applies_the_security_filters(conn, mode) -> None:
    conn.execute(
        """UPDATE chunks SET is_active = false
           WHERE document_id = (SELECT id FROM documents WHERE slug = 'leave-policy')"""
    )
    conn.execute(
        """UPDATE chunks SET allowed_roles = '{hr}'
           WHERE document_id = (SELECT id FROM documents WHERE slug = 'expense-policy')"""
    )
    found = _doc_ids(_retriever(conn, mode=mode).search("leave holiday hotel expense", k=10))
    assert "leave-policy" not in found  # inactive
    assert "expense-policy" not in found  # wrong role
