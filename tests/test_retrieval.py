import pytest
from langchain_mistralai import MistralAIEmbeddings
from langchain_openai import OpenAIEmbeddings

from app.domain import Chunk
from app.retrieval.embeddings import make_embeddings
from app.retrieval.search import ChunkIndex
from tests.fakes import KeywordEmbeddings

VOCAB = ["leave", "holiday", "expense", "hotel", "laptop", "password"]


def chunk(doc_id: str, text: str, page: int = 1, index: int = 0) -> Chunk:
    return Chunk(
        id=f"{doc_id}:{page}:{index}", doc_id=doc_id, source=f"{doc_id}.md", page=page, text=text
    )


CHUNKS = [
    chunk("leave-policy", "Annual leave: 25 days holiday. Leave carries over."),
    chunk("expense-policy", "Hotel limit is 150 per night. Expense claims within 30 days."),
    chunk("it-security", "Report a lost laptop within 1 hour. Password length 14."),
]


# --- search ----------------------------------------------------------------


def test_most_similar_chunk_comes_first() -> None:
    index = ChunkIndex(CHUNKS, KeywordEmbeddings(VOCAB))

    results = index.search("How much leave and holiday do I get?", k=3)

    assert results[0].chunk.id == "leave-policy:1:0"
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


def test_returns_at_most_k_chunks() -> None:
    index = ChunkIndex(CHUNKS, KeywordEmbeddings(VOCAB))

    assert len(index.search("hotel expense", k=2)) == 2
    assert len(index.search("hotel expense", k=10)) == 3


def test_returned_chunks_keep_their_ids_and_text() -> None:
    index = ChunkIndex(CHUNKS, KeywordEmbeddings(VOCAB))

    [top] = index.search("lost laptop password", k=1)

    assert top.chunk == CHUNKS[2]


def test_empty_index_returns_nothing() -> None:
    index = ChunkIndex([], KeywordEmbeddings(VOCAB))

    assert index.search("anything", k=5) == []


# --- embeddings factory ----------------------------------------------------


def test_factory_builds_the_configured_model_at_full_dimension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    embeddings = make_embeddings("openai:text-embedding-3-small")

    assert isinstance(embeddings, OpenAIEmbeddings)
    assert embeddings.model == "text-embedding-3-small"
    assert embeddings.dimensions is None  # never truncated


def test_factory_builds_mistral_embeddings_from_config_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")

    embeddings = make_embeddings("mistralai:mistral-embed")

    assert isinstance(embeddings, MistralAIEmbeddings)
    assert embeddings.model == "mistral-embed"


def test_factory_rejects_a_model_without_provider() -> None:
    with pytest.raises(ValueError, match="provider:model"):
        make_embeddings("text-embedding-3-small")
