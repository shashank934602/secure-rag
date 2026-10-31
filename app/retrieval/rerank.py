"""Reranking (spec 03 D4): a cross-encoder reads the question and each candidate together.

Embedding search compares two separately computed vectors: fast, but coarse. A cross-encoder
reads question + chunk as one input and scores relevance 0–1: precise, but too slow to run on
the whole corpus, so it only reorders the candidates that search already found.
"""

from typing import Protocol

from app.domain import ScoredChunk


class Reranker(Protocol):
    def rerank(self, question: str, candidates: list[ScoredChunk], k: int) -> list[ScoredChunk]:
        """The k most relevant candidates, best first, each scored 0–1."""
        ...


class CrossEncoderReranker:
    """`BAAI/bge-reranker-base` on this machine (CPU or Apple MPS); no text leaves the computer.

    Loaded once (the first download is about 1 GB, then it comes from the local cache).
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base") -> None:
        from sentence_transformers import CrossEncoder  # heavy import: only when used

        self._model = CrossEncoder(model_name)

    def rerank(self, question: str, candidates: list[ScoredChunk], k: int) -> list[ScoredChunk]:
        if not candidates:
            return []
        # One-label cross-encoders apply a sigmoid, so each score is a 0–1 relevance.
        scores = self._model.predict([(question, c.chunk.text) for c in candidates])
        ranked = sorted(zip(candidates, scores, strict=True), key=lambda p: p[1], reverse=True)
        return [ScoredChunk(chunk=c.chunk, score=float(score)) for c, score in ranked[:k]]
