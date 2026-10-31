"""S1 (ISS-020): the migrated schema, the seeded tenant, and what `rag_app` may and may not do.

Needs Docker:   uv run pytest -m db
"""

import psycopg
import pytest

from app.db import connect
from tests.conftest import PgUrls

pytestmark = pytest.mark.db


def _one(url: str, sql: str) -> tuple:
    with psycopg.connect(url) as conn:
        return conn.execute(sql).fetchone()


def _insert_document(conn: psycopg.Connection, slug: str) -> str:
    tenant_id = conn.execute("SELECT id FROM tenants WHERE name = 'Aldermoor'").fetchone()[0]
    return conn.execute(
        """INSERT INTO documents (tenant_id, slug, source, content_hash, allowed_roles)
           VALUES (%s, %s, %s, 'hash', '{employee}') RETURNING id""",
        (tenant_id, slug, f"{slug}.md"),
    ).fetchone()[0]


def _insert_chunk(conn: psycopg.Connection, document_id: str, embedding: list[float]) -> None:
    conn.execute(
        """INSERT INTO chunks (document_id, tenant_id, allowed_roles, page, chunk_index,
                               content, embedding, embedding_model, content_hash)
           SELECT %s, tenant_id, allowed_roles, 1, 0, 'text', %s, 'fake', 'hash'
           FROM documents WHERE id = %s""",
        (document_id, embedding, document_id),
    )


# --- the schema ---------------------------------------------------------------------------


def test_the_four_tables_exist(pg: PgUrls) -> None:
    with psycopg.connect(pg.admin) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    assert {"tenants", "users", "documents", "chunks"} <= {r[0] for r in rows}


def test_embedding_column_holds_1024_numbers(pg: PgUrls) -> None:
    # mistral-embed returns 1,024 numbers (ADR-0005); the column must match exactly.
    (column_type,) = _one(
        pg.admin,
        """SELECT format_type(atttypid, atttypmod) FROM pg_attribute
           WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'""",
    )
    assert column_type == "vector(1024)"


def test_embeddings_have_an_hnsw_cosine_index(pg: PgUrls) -> None:
    with psycopg.connect(pg.admin) as conn:
        rows = conn.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'chunks'").fetchall()
    assert any("USING hnsw" in d and "vector_cosine_ops" in d for (d,) in rows)


def test_aldermoor_is_seeded_with_the_employee_role(pg: PgUrls) -> None:
    assert _one(pg.admin, "SELECT name, roles FROM tenants") == ("Aldermoor", ["employee"])


# --- the rag_app role: least privilege (spec 02 D3) -----------------------------------------


def test_rag_app_is_not_a_superuser_and_cannot_bypass_rls(pg: PgUrls) -> None:
    # Superusers skip row-level security, which protects tenants from each other from Phase 4.
    is_super, bypasses_rls = _one(
        pg.admin, "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'rag_app'"
    )
    assert (is_super, bypasses_rls) == (False, False)


def test_rag_app_can_store_and_read_back_a_chunk(pg: PgUrls) -> None:
    with connect(pg.app) as conn:
        document_id = _insert_document(conn, "leave-policy")
        _insert_chunk(conn, document_id, [0.5] * 1024)
        (embedding,) = conn.execute(
            "SELECT embedding FROM chunks WHERE document_id = %s", (document_id,)
        ).fetchone()
        conn.rollback()
    assert embedding.dimensions() == 1024


def test_rag_app_cannot_change_the_schema(pg: PgUrls) -> None:
    with connect(pg.app) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("CREATE TABLE sneaky (id int)")


def test_rag_app_cannot_drop_a_table(pg: PgUrls) -> None:
    with connect(pg.app) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("DROP TABLE chunks")


# --- the rules the tables enforce -----------------------------------------------------------


def test_a_slug_is_unique_within_a_tenant(pg: PgUrls) -> None:
    with connect(pg.app) as conn:
        _insert_document(conn, "expense-policy")
        with pytest.raises(psycopg.errors.UniqueViolation):
            _insert_document(conn, "expense-policy")
        conn.rollback()


def test_a_wrong_size_embedding_is_rejected(pg: PgUrls) -> None:
    with connect(pg.app) as conn:
        document_id = _insert_document(conn, "it-policy")
        with pytest.raises(psycopg.errors.DataException):
            _insert_chunk(conn, document_id, [0.5] * 1536)  # an OpenAI-sized vector
        conn.rollback()


def test_deleting_a_document_deletes_its_chunks(pg: PgUrls) -> None:
    with connect(pg.app) as conn:
        document_id = _insert_document(conn, "remote-work-policy")
        _insert_chunk(conn, document_id, [0.5] * 1024)
        conn.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        (left,) = conn.execute(
            "SELECT count(*) FROM chunks WHERE document_id = %s", (document_id,)
        ).fetchone()
        conn.rollback()
    assert left == 0


def test_chunks_have_a_keyword_index(pg: PgUrls) -> None:
    # Migration 0002: a generated full-text column, so keyword search needs no extra writes.
    (column_type,) = _one(
        pg.admin,
        """SELECT format_type(atttypid, atttypmod) FROM pg_attribute
           WHERE attrelid = 'chunks'::regclass AND attname = 'content_tsv'""",
    )
    with psycopg.connect(pg.admin) as conn:
        rows = conn.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'chunks'").fetchall()
    assert column_type == "tsvector"
    assert any("USING gin" in d and "content_tsv" in d for (d,) in rows)
