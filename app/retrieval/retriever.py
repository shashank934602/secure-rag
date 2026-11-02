"""The one search interface the answerer depends on (spec 02 D4)."""

from typing import Protocol

from app.domain import AccessScope, ScoredChunk


class Retriever(Protocol):
    """Anything that returns the k chunks most similar to a question, best first, with scores.

    Implementations: `ChunkIndex` (in memory, for unit tests) and `PgRetriever` (Postgres, the app).
    `scope` limits results to one tenant and the user's roles (Phase 4); the in-memory index has no
    ACL and ignores it (local development only).
    """

    def search(
        self, question: str, k: int, scope: AccessScope | None = None
    ) -> list[ScoredChunk]: ...
