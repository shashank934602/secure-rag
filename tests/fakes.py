"""Test doubles for model clients. Real-model quality is measured in eval/, not here."""

import hashlib
import re
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    """Returns the scripted responses in order and records every prompt it was sent."""

    responses: list[str]
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(self, messages: list[BaseMessage], stop: Any = None, **kwargs: Any) -> ChatResult:
        self.calls.append(messages)
        text = self.responses[len(self.calls) - 1]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    @property
    def _llm_type(self) -> str:
        return "scripted"


class KeywordEmbeddings(Embeddings):
    """Bag-of-words vectors over a fixed vocabulary, so similarity is predictable in tests."""

    def __init__(self, vocabulary: list[str], dimensions: int | None = None) -> None:
        self.vocabulary = [word.lower() for word in vocabulary]
        self.dimensions = dimensions  # pad with zeros to fit a fixed column, e.g. vector(1024)

    def _embed(self, text: str) -> list[float]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        # The small constant keeps texts with no vocabulary words from being zero vectors.
        vector = [float(words.count(term)) for term in self.vocabulary] + [0.01]
        if self.dimensions is not None:
            vector += [0.0] * (self.dimensions - len(vector))  # zeros don't change cosine
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class CountingEmbeddings(Embeddings):
    """Deterministic vectors of any size from a hash of the text; counts every text embedded.

    The count is what ingest tests check: unchanged documents must cost zero embedding calls.
    """

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions
        self.embedded: list[str] = []

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [digest[i % len(digest)] / 255 + 0.01 for i in range(self.dimensions)]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.embedded.append(text)
        return self._embed(text)
