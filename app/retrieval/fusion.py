"""Reciprocal Rank Fusion (spec 03 D2): combine ranked lists by rank, not by score."""

from app.domain import ScoredChunk

RRF_K = 60  # the usual constant: dampens the gap between rank 1 and rank 2


def rrf_fuse(lists: list[list[ScoredChunk]], k: int, c: int = RRF_K) -> list[ScoredChunk]:
    """Top k chunks by the sum of 1 / (c + rank) over every list that contains them.

    The lists' own scores are ignored: keyword ranks and cosine similarities live on different
    scales, but ranks are comparable. Ties keep the order in which chunks were first seen.
    """
    totals: dict[str, float] = {}
    chunks = {}
    for ranked in lists:
        for rank, hit in enumerate(ranked, start=1):
            totals[hit.chunk.id] = totals.get(hit.chunk.id, 0.0) + 1 / (c + rank)
            chunks.setdefault(hit.chunk.id, hit.chunk)
    best = sorted(totals, key=lambda chunk_id: totals[chunk_id], reverse=True)[:k]
    return [ScoredChunk(chunk=chunks[chunk_id], score=totals[chunk_id]) for chunk_id in best]
