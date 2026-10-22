"""Vector search in Postgres (spec 02 step 4, ISS-022).

✍️  EXERCISE (S3): write the SQL query in `_SEARCH_SQL` below, then run:

        uv run pytest -m db tests/test_pg_search.py -v

    Your query receives four named values (never paste values into SQL text):
        %(embedding)s   the question's 1,024 numbers
        %(tenant_id)s   the company whose chunks may be returned
        %(roles)s       the asking user's roles, e.g. ['employee']
        %(k)s           how many chunks to return

    It must return one row per chunk, with these six columns in this order:
        slug, source, page, chunk_index, content, score

    Rules (each one is a test):
        1. Only chunks of that tenant, that are active, and that share a role with %(roles)s.
        2. The closest chunks first, at most %(k)s of them.
        3. score = cosine SIMILARITY (1 = same meaning), but `<=>` gives cosine DISTANCE.
        4. Order by the distance itself (not the score), so Postgres can use the HNSW index.
"""

import numpy as np
import psycopg
from langchain_core.embeddings import Embeddings

from app.domain import Chunk, ScoredChunk

_SEARCH_SQL = """
-- ✍️ your query here
"""


class PgRetriever:
    """Finds the chunks most similar to a question, inside one tenant and the user's roles."""

    def __init__(
        self,
        conn: psycopg.Connection,
        embeddings: Embeddings,
        *,
        tenant: str,
        roles: list[str],
    ) -> None:
        row = conn.execute("SELECT id FROM tenants WHERE name = %s", (tenant,)).fetchone()
        if row is None:
            raise ValueError(f"Tenant {tenant!r} not found")
        self._conn = conn
        self._embeddings = embeddings
        self._tenant_id = row[0]
        self._roles = roles

    def search(self, question: str, k: int) -> list[ScoredChunk]:
        if "SELECT" not in _SEARCH_SQL.upper():
            raise NotImplementedError("Write _SEARCH_SQL in app/retrieval/pg_search.py (S3)")
        rows = self._conn.execute(
            _SEARCH_SQL,
            {
                # a numpy array is sent as a pgvector `vector`; a plain list would be an array
                "embedding": np.array(self._embeddings.embed_query(question)),
                "tenant_id": self._tenant_id,
                "roles": self._roles,
                "k": k,
            },
        ).fetchall()
        return [
            ScoredChunk(
                chunk=Chunk(
                    id=f"{slug}:{page}:{chunk_index}",
                    doc_id=slug,
                    source=source,
                    page=page,
                    text=content,
                ),
                score=float(score),
            )
            for slug, source, page, chunk_index, content, score in rows
        ]
