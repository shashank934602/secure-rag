"""Test doubles for model clients. Real-model quality is measured in eval/, not here."""

import re

from langchain_core.embeddings import Embeddings


class KeywordEmbeddings(Embeddings):
    """Bag-of-words vectors over a fixed vocabulary, so similarity is predictable in tests."""

    def __init__(self, vocabulary: list[str]) -> None:
        self.vocabulary = [word.lower() for word in vocabulary]

    def _embed(self, text: str) -> list[float]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        # The small constant keeps texts with no vocabulary words from being zero vectors.
        return [float(words.count(term)) for term in self.vocabulary] + [0.01]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
