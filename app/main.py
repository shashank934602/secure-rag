"""The web API (spec 02 step 5, ISS-023).

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

    POST /v1/ask    {"question": "..."} → {answer, citations, request_id, status}
    GET  /healthz   {"status": "ok"} when the database answers

No authentication until Phase 4, so it must only listen on 127.0.0.1.
Handlers stay thin: validate input, call the answerer, shape the output.
"""

import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from app.answering.answer import Answerer, build_db_answerer
from app.config import get_settings
from app.db import connect
from app.domain import AnswerResult

log = logging.getLogger(__name__)

UNAVAILABLE = "The assistant is temporarily unavailable. Try again."


# Surrounding spaces are removed first, so "   " counts as empty (spec 02 D7: 1–1,000 chars).
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AskRequest(BaseModel):
    question: Question


class CitationOut(BaseModel):
    doc_id: str
    page: int
    source: str


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    request_id: str
    status: Literal["answered", "no_answer"]


def _build_from_settings() -> Answerer:
    return build_db_answerer(get_settings())


def _check_database() -> None:
    with connect(get_settings().database_url) as conn:
        conn.execute("SELECT 1")


def create_app(
    build: Callable[[], Answerer] = _build_from_settings,
    health_check: Callable[[], None] = _check_database,
) -> FastAPI:
    """Build the app. Tests pass a fake `build` and `health_check`; production uses the defaults."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.answerer = build()  # once at start-up, not per request
        yield

    app = FastAPI(title="Secure RAG Assistant", version="0.2.0", lifespan=lifespan)

    @app.post("/v1/ask", response_model=AskResponse)
    def ask(body: AskRequest, request: Request) -> AskResponse | JSONResponse:
        request_id = str(uuid.uuid4())
        try:
            result = request.app.state.answerer.answer(body.question)
        except Exception as error:
            # Log the failure type only: never the question (Invariant 5) or the error text,
            # which can contain keys or internal details. The caller gets a generic message.
            log.error("ask failed request_id=%s error=%s", request_id, type(error).__name__)
            return JSONResponse(status_code=503, content={"detail": UNAVAILABLE})
        return _response(result, request_id)

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        try:
            health_check()
        except Exception as error:
            log.error("healthz failed error=%s", type(error).__name__)
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    return app


def _response(result: AnswerResult, request_id: str) -> AskResponse:
    sources = {(r.chunk.doc_id, r.chunk.page): r.chunk.source for r in result.retrieved}
    return AskResponse(
        answer=result.answer,
        citations=[
            CitationOut(doc_id=c.doc_id, page=c.page, source=sources[(c.doc_id, c.page)])
            for c in result.citations
        ],
        request_id=request_id,
        status=result.status,
    )


app = create_app()
