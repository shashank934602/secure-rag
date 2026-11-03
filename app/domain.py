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


class GuardVerdict(BaseModel):
    """A guard's decision at one point in the flow (GLOSSARY: Guard verdict)."""

    model_config = ConfigDict(frozen=True)

    guard: str  # "input", "context", "output", "grounding"
    decision: Literal["ALLOW", "BLOCK", "DROP", "MASK", "PASS", "FAIL"]
    score: float | None = None
    reason: str = ""


class AnswerResult(BaseModel):
    """The outcome of answering one question: a grounded answer, a No-Answer, or a Refusal."""

    status: Literal["answered", "no_answer", "refused"]
    answer: str
    citations: list[Citation]
    retrieved: list[ScoredChunk]
    prompt_version: str
    verdicts: list[GuardVerdict] = []  # every guard decision, in order (Phase 6 audits them)
    timings: dict[str, float] = {}  # milliseconds per graph step (Phase 6, spec 06 D8)


class AccessScope(BaseModel):
    """Who a search is for: one tenant and the asking user's roles (GLOSSARY: Access scope)."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    roles: list[str]
    can_read_pii: bool = False  # the `pii:read` permission: see sensitive personal data unmasked


class User(BaseModel):
    """An authenticated user. Roles and permissions are read from the database on every request."""

    model_config = ConfigDict(frozen=True)

    id: str
    tenant_id: str
    email: str
    roles: list[str]  # which documents they can read
    permissions: list[str]  # what they can do, e.g. "uploader"

    @property
    def scope(self) -> AccessScope:
        return AccessScope(
            tenant_id=self.tenant_id, roles=self.roles, can_read_pii="pii:read" in self.permissions
        )
