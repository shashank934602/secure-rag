"""In-memory similarity search over chunks (Phase 1; Postgres replaces it in Phase 2)."""

from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from app.domain import Chunk, ScoredChunk


class ChunkIndex:
    """Embeds the chunks once, then returns the top-k most similar chunks for a question."""

    def __init__(self, chunks: list[Chunk], embeddings: Embeddings) -> None:
        self._chunks = {c.id: c for c in chunks}
        self._store = InMemoryVectorStore(embedding=embeddings)
        if chunks:
            self._store.add_texts(texts=[c.text for c in chunks], ids=[c.id for c in chunks])

    def search(self, question: str, k: int) -> list[ScoredChunk]:
        if not self._chunks:
            return []
        hits = self._store.similarity_search_with_score(question, k=k)  # cosine, best first
        return [ScoredChunk(chunk=self._chunks[doc.id], score=score) for doc, score in hits]
