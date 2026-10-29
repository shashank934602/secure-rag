"""Vector search in Postgres (spec 02 step 4, ISS-022).

The query receives four named values (never pasted into the SQL text): %(embedding)s the
question's 1,024 numbers, %(tenant_id)s, %(roles)s the asking user's roles, and %(k)s.
Rules, each one a test in tests/test_pg_search.py:
    1. Only chunks of that tenant, that are active, and that share a role with %(roles)s.
    2. The closest chunks first, at most %(k)s of them.
    3. score = cosine similarity (1 = same meaning) = 1 - the cosine distance from `<=>`.
    4. Order by the distance itself (not the score), so Postgres can use the HNSW index.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import psycopg
from langchain_core.embeddings import Embeddings
from psycopg_pool import ConnectionPool

from app.domain import Chunk, ScoredChunk

# Read it in the order the database runs it: JOIN → WHERE → ORDER BY → LIMIT → SELECT.
_SEARCH_SQL = """
SELECT d.slug, d.source, c.page, c.chunk_index, c.content,
       1 - (c.embedding <=> %(embedding)s) AS score      -- similarity = 1 - cosine distance
FROM chunks c
JOIN documents d ON d.id = c.document_id                  -- each chunk with its document
WHERE c.tenant_id = %(tenant_id)s                         -- only this company's chunks,
  AND c.is_active                                         -- only live ones,
  AND c.allowed_roles && %(roles)s                        -- only ones the user's roles may see
ORDER BY c.embedding <=> %(embedding)s                    -- closest first (uses the HNSW index)
LIMIT %(k)s
"""


class PgRetriever:
    """Finds the chunks most similar to a question, inside one tenant and the user's roles."""

    def __init__(
        self,
        db: psycopg.Connection | ConnectionPool,
        embeddings: Embeddings,
        *,
        tenant: str,
        roles: list[str],
    ) -> None:
        self._db = db  # one connection (tests, CLI) or a pool (the API)
        self._embeddings = embeddings
        self._roles = roles
        with self._connection() as conn:
            row = conn.execute("SELECT id FROM tenants WHERE name = %s", (tenant,)).fetchone()
        if row is None:
            raise ValueError(f"Tenant {tenant!r} not found")
        self._tenant_id = row[0]

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        if isinstance(self._db, ConnectionPool):
            with self._db.connection() as conn:  # checked alive, returned to the pool after
                yield conn
        else:
            yield self._db

    def search(self, question: str, k: int) -> list[ScoredChunk]:
        params = {
            # a numpy array is sent as a pgvector `vector`; a plain list would be an array
            "embedding": np.array(self._embeddings.embed_query(question)),
            "tenant_id": self._tenant_id,
            "roles": self._roles,
            "k": k,
        }
        with self._connection() as conn:
            rows = conn.execute(_SEARCH_SQL, params).fetchall()
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
