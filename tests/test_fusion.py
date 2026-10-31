"""S1 (ISS-030): Reciprocal Rank Fusion — combine ranked lists by rank, not by score."""

import pytest

from app.domain import Chunk, ScoredChunk
from app.retrieval.fusion import rrf_fuse


def _hit(name: str, score: float = 0.0) -> ScoredChunk:
    chunk = Chunk(id=f"{name}:1:0", doc_id=name, source=f"{name}.md", page=1, text=name)
    return ScoredChunk(chunk=chunk, score=score)


def _ids(hits: list[ScoredChunk]) -> list[str]:
    return [h.chunk.doc_id for h in hits]


def test_a_chunk_found_by_both_lists_rises_to_the_top() -> None:
    dense = [_hit("x"), _hit("y"), _hit("z")]
    keyword = [_hit("z"), _hit("w")]

    fused = rrf_fuse([dense, keyword], k=4)

    # z: 1/63 + 1/61 beats x: 1/61; y and w tie at 1/62, y was seen first.
    assert _ids(fused) == ["z", "x", "y", "w"]
    assert fused[0].score == pytest.approx(1 / 63 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 61)


def test_original_scores_are_ignored() -> None:
    # Keyword scores (ts_rank) and similarities live on different scales; only ranks count.
    dense = [_hit("a", 0.9), _hit("b", 0.8)]
    keyword = [_hit("b", 0.001), _hit("a", 50.0)]
    assert rrf_fuse([dense, keyword], k=2)[0].score == rrf_fuse([keyword, dense], k=2)[0].score


def test_k_limits_the_result() -> None:
    assert len(rrf_fuse([[_hit("a"), _hit("b"), _hit("c")]], k=2)) == 2


def test_empty_lists_give_nothing() -> None:
    assert rrf_fuse([[], []], k=5) == []


def test_one_list_keeps_its_order() -> None:
    assert _ids(rrf_fuse([[_hit("a"), _hit("b")], []], k=5)) == ["a", "b"]
