"""The real cross-encoder reranker (ISS-031). Runs locally; the first run downloads ~1 GB.

Skipped by default. Run with `uv run pytest -m live`.
"""

import pytest

from app.domain import Chunk, ScoredChunk
from app.retrieval.rerank import CrossEncoderReranker

pytestmark = pytest.mark.live


def _candidate(doc_id: str, text: str) -> ScoredChunk:
    chunk = Chunk(id=f"{doc_id}:1:0", doc_id=doc_id, source=f"{doc_id}.md", page=1, text=text)
    return ScoredChunk(chunk=chunk, score=0.0)


@pytest.fixture(scope="module")
def reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker()


def test_the_relevant_chunk_is_ranked_first_with_a_0_to_1_score(reranker) -> None:
    candidates = [
        _candidate("expense-policy", "The maximum nightly hotel rate is £150 outside London."),
        _candidate("annual-leave-policy", "Full-time employees receive 25 days of paid annual leave."),
    ]

    ranked = reranker.rerank("How many days of annual leave do I get?", candidates, k=2)

    assert ranked[0].chunk.doc_id == "annual-leave-policy"
    assert 0.0 <= ranked[1].score < ranked[0].score <= 1.0


def test_no_candidates_give_nothing(reranker) -> None:
    assert reranker.rerank("anything", [], k=5) == []
