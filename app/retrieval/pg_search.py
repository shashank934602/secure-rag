"""Search in Postgres: dense (vector), keyword (full text), or hybrid (both, fused with RRF).

Dense search: spec 02 step 4, ISS-022. Keyword and hybrid: spec 03 D1–D3, ISS-030.

The query receives four named values (never pasted into the SQL text): %(embedding)s the
question's 1,024 numbers, %(tenant_id)s, %(roles)s the asking user's roles, and %(k)s.
Rules, each one a test in tests/test_pg_search.py:
    1. Only chunks of that tenant, that are active, and that share a role with %(roles)s.
    2. The closest chunks first, at most %(k)s of them.
    3. score = cosine similarity (1 = same meaning) = 1 - the cosine distance from `<=>`.
    4. Order by the distance itself (not the score), so Postgres can use the HNSW index.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import numpy as np
import psycopg
from langchain_core.embeddings import Embeddings
from psycopg_pool import ConnectionPool

from app.domain import Chunk, ScoredChunk
from app.retrieval.fusion import rrf_fuse

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

# Keyword search: chunks containing any of the question's words, best-matching first, with the
# same security filters. `ts_rank_cd` rewards chunks where the words are many and close together.
_KEYWORD_SQL = """
SELECT d.slug, d.source, c.page, c.chunk_index, c.content,
       ts_rank_cd(c.content_tsv, query) AS score
FROM chunks c
JOIN documents d ON d.id = c.document_id,
     websearch_to_tsquery('english', %(words)s) AS query
WHERE c.tenant_id = %(tenant_id)s
  AND c.is_active
  AND c.allowed_roles && %(roles)s
  AND c.content_tsv @@ query                              -- contains at least one of the words
ORDER BY score DESC
LIMIT %(k)s
"""

Mode = Literal["dense", "keyword", "hybrid"]


def keyword_query(question: str) -> str:
    """The question's words joined with "or", so a chunk matching *any* of them is found.

    Only letters and digits survive: quotes, minus signs, and the word "or" itself would
    otherwise be read as search operators. Stop words ("the", "what") are dropped by Postgres.
    """
    words = [w for w in re.findall(r"[^\W_]+", question) if w.lower() != "or"]
    return " or ".join(words)


class PgRetriever:
    """Finds the chunks most similar to a question, inside one tenant and the user's roles."""

    def __init__(
        self,
        db: psycopg.Connection | ConnectionPool,
        embeddings: Embeddings,
        *,
        tenant: str,
        roles: list[str],
        mode: Mode = "dense",
        candidates: int = 20,
    ) -> None:
        self._db = db  # one connection (tests, CLI) or a pool (the API)
        self._embeddings = embeddings
        self._roles = roles
        self._mode = mode
        self._candidates = candidates  # per list, before hybrid fusion
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
        if self._mode == "dense":
            return self._dense(question, k)
        if self._mode == "keyword":
            return self._keyword(question, k)
        n = max(k, self._candidates)
        return rrf_fuse([self._dense(question, n), self._keyword(question, n)], k)

    def _dense(self, question: str, k: int) -> list[ScoredChunk]:
        # a numpy array is sent as a pgvector `vector`; a plain list would be an array
        embedding = np.array(self._embeddings.embed_query(question))
        return self._run(_SEARCH_SQL, {"embedding": embedding, "k": k})

    def _keyword(self, question: str, k: int) -> list[ScoredChunk]:
        words = keyword_query(question)
        if not words:
            return []
        return self._run(_KEYWORD_SQL, {"words": words, "k": k})

    def _run(self, sql: str, params: dict) -> list[ScoredChunk]:
        params = {**params, "tenant_id": self._tenant_id, "roles": self._roles}
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
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
