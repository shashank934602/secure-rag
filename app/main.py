"""The web API (spec 02 step 5, ISS-023).

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

    POST /v1/ask    {"question": "..."} → {answer, citations, request_id, status}
                    needs `Authorization: Bearer <token>`; answers as that user (spec 04 D6)
    PATCH /v1/documents/{doc_id}/acl  {"allowed_roles": [...]} → who may read it (needs `uploader`)
    GET  /v1/audit/requests/{id}, /v1/audit/requests?…, /v1/audit/verify  (needs `auditor`)
    GET  /healthz   {"status": "ok"} when the database answers (no token)
    GET  /          a small demo page: paste a token, ask, see the answer and its sources

Tokens: `python -m app.auth token --tenant Aldermoor --email alice@aldermoor.example.com`.
Bound to 127.0.0.1 until the HTTPS proxy of production Stage A (ISS-075); limits: app/limits.py.
Handlers stay thin: validate input, call the answerer, shape the output.
"""

import functools
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path as FilePath
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field, StringConstraints
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.answering.answer import Answerer, build_db_answerer
from app.audit.queries import AuditAccessError, get_request, list_requests, verify_tenant
from app.audit.recorder import AuditRecorder
from app.auth import AuthError, TokenKeys, authenticate
from app.config import get_settings
from app.db import connect, make_pool
from app.documents import AclError, change_acl
from app.domain import AnswerResult, User
from app.guards.grounding import JUDGE_PROMPT_VERSION
from app.limits import LimiterUnavailable, LimitExceeded, build_limits, total_tokens

log = logging.getLogger(__name__)
# One JSON line per request: who, outcome, time per step. Never the question or answer
# (Invariant 5): those live, redacted, in the audit trail (spec 06 D8).
request_log = logging.getLogger("app.requests")

UNAVAILABLE = "The assistant is temporarily unavailable. Try again."
RETRY_AFTER = {"Retry-After": "30"}  # a 503 is temporary (outage, provider rate limit)
MAX_BODY_BYTES = 16_384  # a 1,000-character question fits many times over (tester T-3)
TOO_LARGE = "Request body too large"
STATIC = FilePath(__file__).resolve().parent / "static"
# The demo page loads only its own files and talks only to this API (spec 08 D5). Not applied to
# /docs, whose Swagger UI loads from a CDN.
PAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class BodyLimit:
    """Refuse request bodies over `max_bytes` with 413, however they are sent.

    A declared Content-Length is checked before anything is read. A chunked upload declares no
    length, so its bytes are counted as they arrive and reading stops at the limit (tester
    v0.6.0 T-1: a 3 MB chunked body used to be read whole, then rejected as 422).
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope["headers"]).get(b"content-length", b"")
        if length.isdigit() and int(length) > self.max_bytes:
            await JSONResponse(status_code=413, content={"detail": TOO_LARGE})(scope, receive, send)
            return
        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:  # FastAPI passes this through as a 413
                    raise HTTPException(status_code=413, detail=TOO_LARGE)
            return message

        await self.app(scope, counted, send)


class ErrorOut(BaseModel):
    detail: str


def _error_docs(*codes: int) -> dict:
    """OpenAPI entries for the error responses a route really returns (tester T-1)."""
    meaning = {
        401: "Missing, invalid, or expired token",
        403: "The user lacks the permission",
        404: "Not found in the user's tenant",
        413: "Request body too large",
        429: "Rate limit or the organisation's daily token budget reached; see Retry-After",
        503: "Temporarily unavailable (a guard, model, or the database); retry later",
    }
    return {code: {"model": ErrorOut, "description": meaning[code]} for code in codes}


def _unavailable() -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": UNAVAILABLE}, headers=RETRY_AFTER)


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
    status: Literal["answered", "no_answer", "refused"]


def _build_from_settings() -> Answerer:
    return build_db_answerer(get_settings())


def _authenticator_from_settings() -> Callable[[str], User]:
    settings = get_settings()
    keys = TokenKeys.from_settings(settings)  # refuses to start without JWT_PUBLIC_KEY
    pool = make_pool(settings.database_url, name="rag-auth")
    return lambda token: authenticate(token, keys=keys, db=pool)


def _recorder_from_settings() -> AuditRecorder:
    settings = get_settings()
    return AuditRecorder(
        make_pool(settings.database_url, name="rag-audit"), settings.audit_hmac_key
    )


def _database_from_settings() -> ConnectionPool:
    return make_pool(get_settings().database_url, name="rag-api")


def _limits_from_settings():
    return build_limits(get_settings())


def _check_database() -> None:
    with connect(get_settings().database_url) as conn:
        conn.execute("SELECT 1")


def create_app(
    build: Callable[[], Answerer] = _build_from_settings,
    health_check: Callable[[], None] = _check_database,
    authenticator: Callable[[], Callable[[str], User]] = _authenticator_from_settings,
    database: Callable[[], object] = _database_from_settings,
    recorder: Callable[[], object] = _recorder_from_settings,
    limits: Callable[[], object] = _limits_from_settings,
) -> FastAPI:
    """Build the app. Tests pass fakes for each part; production uses the defaults."""
    get_database = functools.cache(database)  # opened on first use, not at start-up

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.answerer = build()  # once at start-up, not per request
        warm_up = getattr(app.state.answerer, "warm_up", None)
        if warm_up is not None:
            warm_up()  # load local models now, so the first user doesn't wait for them
        app.state.authenticate = authenticator()
        app.state.recorder = recorder()  # refuses to start without AUDIT_HMAC_KEY
        app.state.limits = limits()  # Redis when REDIS_URL is set, else this process's memory
        yield

    if not request_log.handlers:  # show the request lines in the server output
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        request_log.addHandler(handler)
        request_log.setLevel(logging.INFO)

    app = FastAPI(title="Secure RAG Assistant", version="0.6.0", lifespan=lifespan)

    app.add_middleware(BodyLimit)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def page_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers.update(PAGE_HEADERS)
        return response

    @app.get("/", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Say what is wrong and where, without echoing the user's input back (tester T-3).
        problems = [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": problems})

    @app.post("/v1/ask", response_model=AskResponse, responses=_error_docs(401, 413, 429, 503))
    def ask(
        body: AskRequest, request: Request, user: Annotated[User, Depends(allowed_user)]
    ) -> AskResponse | JSONResponse:
        request_id, started = str(uuid.uuid4()), time.perf_counter()
        answerer, audit = request.app.state.answerer, request.app.state.recorder
        line = functools.partial(_log_request, request_id, user, started)
        limits = request.app.state.limits
        try:  # book tokens before any model call; past today's budget → 429 (spec 09 D3)
            reserved = limits.reserve(user)
        except LimitExceeded as error:
            line("rate_limited", reason="token_budget")
            return _too_many(error)
        except LimiterUnavailable:
            line("error", error="limiter")
            return _unavailable()  # fail closed (spec 09 D4)
        used = 0  # tokens really spent; the booking is corrected to this on every way out

        def answer_and_record() -> AskResponse | JSONResponse:
            try:  # recorded before anything runs, so even a crash leaves a trace (spec 06 D5)
                audit.start(request_id, user, body.question)
            except Exception as error:
                log.error(
                    "audit start failed request_id=%s error=%s", request_id, type(error).__name__
                )
                line("error", error="audit_start")
                return _unavailable()  # no audit, no answer (D6)
            try:
                result = answerer.answer(body.question, scope=user.scope)
            except Exception as error:
                # Log the failure type only: never the question (Invariant 5) or the error text,
                # which can contain keys or internal details. The caller gets a generic message.
                log.error("ask failed request_id=%s error=%s", request_id, type(error).__name__)
                progress = getattr(error, "progress", None)  # what ran before it failed (T-2)
                try:
                    audit.fail(request_id, user, type(error).__name__, latency_ms=_ms(started),
                               progress=progress)  # fmt: skip
                except Exception as audit_error:
                    log.error("audit fail failed request_id=%s error=%s", request_id,
                              type(audit_error).__name__)  # fmt: skip
                line("error", progress.timings if progress else {}, error=type(error).__name__,
                     failed_step=progress.failed_step if progress else None)  # fmt: skip
                return _unavailable()
            nonlocal used
            used = total_tokens(result.usage)
            judge = JUDGE_PROMPT_VERSION if answerer.grounding_judge is not None else None
            try:
                audit.finish(request_id, user, result, latency_ms=_ms(started),
                             model=answerer.model_label, judge_prompt_version=judge)  # fmt: skip
            except Exception as error:
                log.error(
                    "audit finish failed request_id=%s error=%s", request_id, type(error).__name__
                )
                line("error", result.timings, error="audit_finish")
                return _unavailable()  # an answer that can't be explained isn't given (D6)
            line(result.status, result.timings)
            return _response(result, request_id)

        try:
            return answer_and_record()
        finally:
            try:
                limits.settle(user, reserved, used)
            except LimiterUnavailable:
                log.error("token budget update failed request_id=%s", request_id)

    @app.patch("/v1/documents/{doc_id}/acl", responses=_error_docs(401, 403, 404, 413, 429, 503))
    def update_acl(
        request: Request,
        body: AclChange,
        user: Annotated[User, Depends(allowed_user)],
        doc_id: Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9-]{0,199}$")],
    ) -> JSONResponse:
        audit = request.app.state.recorder
        try:
            changed = change_acl(
                get_database(), user, doc_id, body.allowed_roles,
                audit=lambda conn, change: audit.acl_changed(conn, user, change),
            )  # fmt: skip
        except AclError as error:
            try:  # a refused attempt is evidence too
                audit.acl_refused(user, doc_id, error.status, error.detail)
            except Exception as audit_error:
                log.error("audit acl_refused failed error=%s", type(audit_error).__name__)
            return JSONResponse(status_code=error.status, content={"detail": error.detail})
        except Exception as error:
            log.error("acl change failed error=%s", type(error).__name__)
            return _unavailable()
        return JSONResponse(status_code=200, content=changed)

    def _audit_call(read: Callable[[], object]) -> JSONResponse:
        try:
            return JSONResponse(status_code=200, content=read())
        except AuditAccessError as error:
            return JSONResponse(status_code=error.status, content={"detail": error.detail})
        except Exception as error:
            log.error("audit read failed error=%s", type(error).__name__)
            return _unavailable()

    @app.get("/v1/audit/requests/{request_id}", responses=_error_docs(401, 403, 404, 429, 503))
    def audit_request(
        request_id: uuid.UUID, user: Annotated[User, Depends(allowed_user)]
    ) -> JSONResponse:
        """One request with its sources and every decision, in order (needs `auditor`)."""
        return _audit_call(lambda: get_request(get_database(), user, str(request_id)))

    @app.get("/v1/audit/requests", responses=_error_docs(401, 403, 429, 503))
    def audit_search(
        user: Annotated[User, Depends(allowed_user)],
        status: Literal["started", "answered", "no_answer", "refused", "error"] | None = None,
        user_id: uuid.UUID | None = None,
        since: datetime | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> JSONResponse:
        """Search this tenant's requests, newest first (needs `auditor`)."""

        def search() -> dict:
            matches = list_requests(
                get_database(),
                user,
                status=status,
                user_id=str(user_id) if user_id else None,
                since=since,
                limit=limit,
            )
            return {"requests": matches}

        return _audit_call(search)

    @app.get("/v1/audit/verify", responses=_error_docs(401, 403, 429, 503))
    def audit_verify(user: Annotated[User, Depends(allowed_user)]) -> JSONResponse:
        """Recompute this tenant's hash chain; names the first edited or missing event."""
        return _audit_call(lambda: verify_tenant(get_database(), user))

    @app.get("/healthz", responses=_error_docs(503))
    def healthz(request: Request) -> JSONResponse:
        try:
            health_check()
            request.app.state.limits.ping()  # Redis down = every request refused: not healthy
        except Exception as error:
            log.error("healthz failed error=%s", type(error).__name__)
            return JSONResponse(
                status_code=503, content={"status": "unavailable"}, headers=RETRY_AFTER
            )
        return JSONResponse(status_code=200, content={"status": "ok"})

    @app.head("/healthz", include_in_schema=False)  # for load balancers (tester T-3)
    def healthz_head(request: Request) -> JSONResponse:
        return healthz(request)

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
        raise HTTPException(status_code=503, detail=UNAVAILABLE, headers=RETRY_AFTER) from None


def allowed_user(request: Request, user: Annotated[User, Depends(current_user)]) -> User:
    """The authenticated user, within their rate limits (spec 09 D2): 429 when over, 503 when the
    limiter itself can't be reached (fail closed, D4). Logged, not audited (D7)."""
    try:
        request.app.state.limits.check_rate(user)
    except LimitExceeded as error:
        entry = {"user_id": user.id, "tenant_id": user.tenant_id, "status": "rate_limited",
                 "path": request.url.path}  # fmt: skip
        request_log.info(json.dumps(entry))
        retry = {"Retry-After": str(error.retry_after_s)}
        raise HTTPException(status_code=429, detail=error.detail, headers=retry) from None
    except LimiterUnavailable:
        log.error("rate limiter unavailable")
        raise HTTPException(status_code=503, detail=UNAVAILABLE, headers=RETRY_AFTER) from None
    return user


def _too_many(error: LimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": error.detail},
                        headers={"Retry-After": str(error.retry_after_s)})  # fmt: skip


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"}
    )


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _log_request(
    request_id: str,
    user: User,
    started: float,
    status: str,
    timings: dict[str, float] | None = None,
    **extra: str | None,
) -> None:
    """One JSON line per request, failures included (tester v0.6.0 T-2): who, outcome, time per
    step, and for a failure its error type. Never the question or answer (Invariant 5)."""
    line = {"request_id": request_id, "user_id": user.id, "tenant_id": user.tenant_id,
            "status": status, "latency_ms": _ms(started), "timings_ms": timings or {}}  # fmt: skip
    line |= {key: value for key, value in extra.items() if value is not None}
    request_log.info(json.dumps(line))


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
