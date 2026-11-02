"""The web API: POST /v1/ask and GET /healthz (ISS-023), now behind tokens (ISS-036). Offline."""

import uuid

from fastapi.testclient import TestClient

from app.answering.answer import NO_ANSWER, Answerer
from app.auth import AuthError
from app.domain import AccessScope, Chunk, User
from app.main import create_app
from app.retrieval.search import ChunkIndex
from tests.fakes import KeywordEmbeddings, ScriptedChatModel

VOCAB = ["leave", "holiday", "hotel"]
CHUNKS = [
    Chunk(
        id="leave-policy:1:0",
        doc_id="leave-policy",
        source="leave-policy.md",
        page=1,
        text="Annual leave is 25 days.",
    ),
    Chunk(
        id="expense-policy:1:0",
        doc_id="expense-policy",
        source="expense-policy.md",
        page=1,
        text="Hotel limit is 190 pounds.",
    ),
]


ALICE = User(
    id="u-alice",
    tenant_id="t-aldermoor",
    email="alice@aldermoor.example.com",
    roles=["employee"],
    permissions=[],
)


def _authenticate(token: str) -> User:
    if token != "good-token":
        raise AuthError("bad token")
    return ALICE


def _test_client(build, health_check) -> TestClient:
    """A client that sends a valid token by default; tests about auth override the header."""
    app = create_app(build=build, health_check=health_check, authenticator=lambda: _authenticate)
    return TestClient(app, headers={"Authorization": "Bearer good-token"})


def _answerer(*responses: str) -> Answerer:
    return Answerer(
        index=ChunkIndex(CHUNKS, KeywordEmbeddings(VOCAB)),
        chat_model=ScriptedChatModel(responses=list(responses)),
        top_k=2,
    )


def _client(*responses: str, healthy: bool = True) -> TestClient:
    def health_check() -> None:
        if not healthy:
            raise ConnectionError("database down")

    return _test_client(lambda: _answerer(*responses), health_check)


# --- POST /v1/ask: answers -------------------------------------------------------------------


def test_ask_returns_the_answer_with_citations_and_sources() -> None:
    with _client("You get 25 days [leave-policy:1].") as client:
        response = client.post("/v1/ask", json={"question": "How much leave?"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["answer"] == "You get 25 days [leave-policy:1]."
    assert body["citations"] == [{"doc_id": "leave-policy", "page": 1, "source": "leave-policy.md"}]
    uuid.UUID(body["request_id"])  # a valid id, for support and (from Phase 6) the audit trail


def test_ask_returns_no_answer_as_a_normal_200() -> None:
    # "I don't know" is a correct, successful outcome, not an error.
    with _client(NO_ANSWER) as client:
        body = client.post("/v1/ask", json={"question": "What is the CEO's salary?"}).json()

    assert (body["status"], body["answer"], body["citations"]) == ("no_answer", NO_ANSWER, [])


def test_every_request_gets_its_own_id() -> None:
    with _client(NO_ANSWER, NO_ANSWER) as client:
        first = client.post("/v1/ask", json={"question": "a"}).json()["request_id"]
        second = client.post("/v1/ask", json={"question": "b"}).json()["request_id"]

    assert first != second


def test_the_answerer_is_built_once_not_per_request() -> None:
    builds = []

    def build() -> Answerer:
        builds.append(1)
        return _answerer(NO_ANSWER, NO_ANSWER)

    with _test_client(build, lambda: None) as client:
        client.post("/v1/ask", json={"question": "a"})
        client.post("/v1/ask", json={"question": "b"})

    assert len(builds) == 1


# --- POST /v1/ask: bad input → 422 -------------------------------------------------------------


def test_bad_questions_are_rejected_with_422() -> None:
    with _client() as client:
        for payload in (
            {},  # missing
            {"question": ""},  # empty
            {"question": "   "},  # only spaces
            {"question": "x" * 1001},  # too long
            {"question": 42},  # not text
        ):
            assert client.post("/v1/ask", json=payload).status_code == 422, payload


def test_a_1000_character_question_is_accepted() -> None:
    with _client(NO_ANSWER) as client:
        assert client.post("/v1/ask", json={"question": "x" * 1000}).status_code == 200


# --- POST /v1/ask: failures → 503, nothing internal leaks ---------------------------------------


def test_a_model_failure_is_a_503_without_internal_details() -> None:
    class BrokenModel(ScriptedChatModel):
        def _generate(self, *args, **kwargs):
            raise RuntimeError("upstream timeout; api_key=sk-secret-123")

    answerer = Answerer(
        index=ChunkIndex(CHUNKS, KeywordEmbeddings(VOCAB)),
        chat_model=BrokenModel(responses=[]),
        top_k=2,
    )
    with _test_client(lambda: answerer, lambda: None) as client:
        response = client.post("/v1/ask", json={"question": "How much leave?"})

    assert response.status_code == 503
    assert response.json() == {"detail": "The assistant is temporarily unavailable. Try again."}
    assert "sk-secret" not in response.text and "Traceback" not in response.text


# --- GET /healthz ------------------------------------------------------------------------------


def test_healthz_is_ok_when_the_database_answers() -> None:
    with _client() as client:
        response = client.get("/healthz")

    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_healthz_is_503_when_the_database_is_down() -> None:
    with _client(healthy=False) as client:
        response = client.get("/healthz")

    assert (response.status_code, response.json()) == (503, {"status": "unavailable"})


# --- authentication (Phase 4, ISS-036) ---------------------------------------------------------


def test_ask_without_a_token_is_401() -> None:
    with _client(NO_ANSWER) as client:
        response = client.post(
            "/v1/ask", json={"question": "How much leave?"}, headers={"Authorization": ""}
        )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Not authenticated"}


def test_ask_with_a_bad_token_or_scheme_is_401() -> None:
    with _client(NO_ANSWER) as client:
        for header in ("Bearer forged-token", "Basic good-token", "good-token"):
            response = client.post(
                "/v1/ask", json={"question": "leave?"}, headers={"Authorization": header}
            )
            assert response.status_code == 401, header


def test_the_question_is_answered_in_the_users_scope() -> None:
    class SpyIndex(ChunkIndex):
        scopes: list = []

        def search(self, question, k, scope=None):
            self.scopes.append(scope)
            return super().search(question, k, scope)

    answerer = Answerer(
        index=SpyIndex(CHUNKS, KeywordEmbeddings(VOCAB)),
        chat_model=ScriptedChatModel(responses=[NO_ANSWER]),
        top_k=2,
    )
    with _test_client(lambda: answerer, lambda: None) as client:
        client.post("/v1/ask", json={"question": "How much leave?"})

    assert SpyIndex.scopes == [AccessScope(tenant_id="t-aldermoor", roles=["employee"])]


def test_an_auth_outage_is_503_not_401() -> None:
    def down(token: str) -> User:
        raise ConnectionError("database down")

    app = create_app(
        build=lambda: _answerer(), health_check=lambda: None, authenticator=lambda: down
    )
    with TestClient(app, headers={"Authorization": "Bearer good-token"}) as client:
        response = client.post("/v1/ask", json={"question": "leave?"})

    assert response.status_code == 503  # fail closed, but don't tell a valid user they're invalid


def test_healthz_needs_no_token() -> None:
    with _client() as client:
        assert client.get("/healthz", headers={"Authorization": ""}).status_code == 200
