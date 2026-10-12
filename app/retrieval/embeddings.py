"""The one place embedding clients are created: providers stay swappable, tests inject fakes."""

from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings


def make_embeddings(model: str) -> Embeddings:
    """Build an embeddings client from a 'provider:model' string, at the model's full dimension."""
    provider, sep, name = model.partition(":")
    if not sep or not provider or not name:
        raise ValueError(f"Embedding model must be 'provider:model', got {model!r}")
    return init_embeddings(name, provider=provider)
