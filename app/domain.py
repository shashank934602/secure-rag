"""Domain types shared across modules. Names follow GLOSSARY.md."""

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
