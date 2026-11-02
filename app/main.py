"""The web API (spec 02 step 5, ISS-023).

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

    POST /v1/ask    {"question": "..."} → {answer, citations, request_id, status}
                    needs `Authorization: Bearer <token>`; answers as that user (spec 04 D6)
    PATCH /v1/documents/{doc_id}/acl  {"allowed_roles": [...]} → who may read it (needs `uploader`)
    GET  /healthz   {"status": "ok"} when the database answers (no token)

Tokens: `python -m app.auth token --tenant Aldermoor --email alice@aldermoor.example.com`.
Still bound to 127.0.0.1 until rate limiting exists (ISS-040).
Handlers stay thin: validate input, call the answerer, shape the output.
"""

import functools
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field, StringConstraints

from app.answering.answer import Answerer, build_db_answerer
from app.auth import AuthError, authenticate
from app.config import get_settings
from app.db import connect, make_pool
from app.documents import AclError, change_acl
from app.domain import AnswerResult, User

log = logging.getLogger(__name__)

UNAVAILABLE = "The assistant is temporarily unavailable. Try again."


# Surrounding spaces are removed first, so "   " counts as empty (spec 02 D7: 1–1,000 chars).
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class AskRequest(BaseModel):
    question: Question


RoleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class AclChange(BaseModel):
    allowed_roles: list[RoleName] = Field(min_length=1, max_length=50)


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


def _authenticator_from_settings() -> Callable[[str], User]:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set (see .env.example)")
    pool = make_pool(settings.database_url, name="rag-auth")
    return lambda token: authenticate(token, secret=settings.jwt_secret, db=pool)


def _database_from_settings() -> ConnectionPool:
    return make_pool(get_settings().database_url, name="rag-api")


def _check_database() -> None:
    with connect(get_settings().database_url) as conn:
        conn.execute("SELECT 1")


def create_app(
    build: Callable[[], Answerer] = _build_from_settings,
    health_check: Callable[[], None] = _check_database,
    authenticator: Callable[[], Callable[[str], User]] = _authenticator_from_settings,
    database: Callable[[], object] = _database_from_settings,
) -> FastAPI:
    """Build the app. Tests pass fakes for each part; production uses the defaults."""
    get_database = functools.cache(database)  # opened on first use, not at start-up

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.answerer = build()  # once at start-up, not per request
        app.state.authenticate = authenticator()
        yield

    app = FastAPI(title="Secure RAG Assistant", version="0.4.0", lifespan=lifespan)

    @app.post("/v1/ask", response_model=AskResponse)
    def ask(
        body: AskRequest, request: Request, user: Annotated[User, Depends(current_user)]
    ) -> AskResponse | JSONResponse:
        request_id = str(uuid.uuid4())
        try:
            result = request.app.state.answerer.answer(body.question, scope=user.scope)
        except Exception as error:
            # Log the failure type only: never the question (Invariant 5) or the error text,
            # which can contain keys or internal details. The caller gets a generic message.
            log.error("ask failed request_id=%s error=%s", request_id, type(error).__name__)
            return JSONResponse(status_code=503, content={"detail": UNAVAILABLE})
        return _response(result, request_id)

    @app.patch("/v1/documents/{doc_id}/acl")
    def update_acl(
        body: AclChange,
        user: Annotated[User, Depends(current_user)],
        doc_id: Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]{0,199}$")],
    ) -> JSONResponse:
        try:
            changed = change_acl(get_database(), user, doc_id, body.allowed_roles)
        except AclError as error:
            return JSONResponse(status_code=error.status, content={"detail": error.detail})
        except Exception as error:
            log.error("acl change failed error=%s", type(error).__name__)
            return JSONResponse(status_code=503, content={"detail": UNAVAILABLE})
        return JSONResponse(status_code=200, content=changed)

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        try:
            health_check()
        except Exception as error:
            log.error("healthz failed error=%s", type(error).__name__)
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return JSONResponse(status_code=200, content={"status": "ok"})

    return app


_bearer = HTTPBearer(auto_error=False)  # we raise our own 401, with a fixed message


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The user behind `Authorization: Bearer <token>`; 401 if there is none or it's invalid."""
    if credentials is None:
        raise _unauthorized()
    try:
        return request.app.state.authenticate(credentials.credentials)
    except AuthError:
        raise _unauthorized() from None
    except Exception as error:  # e.g. the database is down: refuse, but don't blame the token
        log.error("auth failed error=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail=UNAVAILABLE) from None


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )


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
