"""The one search interface the answerer depends on (spec 02 D4)."""

from typing import Protocol

from app.domain import ScoredChunk


class Retriever(Protocol):
    """Anything that returns the k chunks most similar to a question, best first, with scores.

    Implementations: `ChunkIndex` (in memory, for unit tests) and `PgRetriever` (Postgres, the app).
    """

    def search(self, question: str, k: int) -> list[ScoredChunk]: ...
