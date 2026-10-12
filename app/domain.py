"""Domain types shared across modules. Names follow GLOSSARY.md."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Page(BaseModel):
    """One page of a document's text. Non-paged formats are a single page 1."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    source: str
    page: int
    text: str


class Chunk(BaseModel):
    """A contiguous slice of one page, embedded and retrieved as a unit."""

    model_config = ConfigDict(frozen=True)

    id: str  # "doc_id:page:index"
    doc_id: str
    source: str
    page: int
    text: str


class ScoredChunk(BaseModel):
    """A chunk returned by search, with its similarity to the question (higher is closer)."""

    model_config = ConfigDict(frozen=True)

    chunk: Chunk
    score: float


class Citation(BaseModel):
    """A `[doc_id:page]` reference in an answer; valid only if it points to a retrieved chunk."""

    model_config = ConfigDict(frozen=True)

    doc_id: str
    page: int

    def __str__(self) -> str:
        return f"{self.doc_id}:{self.page}"


class AnswerResult(BaseModel):
    """The outcome of answering one question: a grounded answer with citations, or a No-Answer."""

    status: Literal["answered", "no_answer"]
    answer: str
    citations: list[Citation]
    retrieved: list[ScoredChunk]
    prompt_version: str
