"""S2 (ISS-051): every request is recorded — at the start, at the end, and on failure — without
raw text at rest (Invariant 5).

Needs Docker:   uv run pytest -m db
"""

import hashlib
import hmac
import uuid

import psycopg
import pytest

from app.audit.log import verify
from app.audit.recorder import AuditRecorder
from app.db import connect
from app.domain import AnswerResult, Chunk, Citation, GuardVerdict, Progress, ScoredChunk, User
from tests.conftest import PgUrls

pytestmark = pytest.mark.db
KEY = "test-audit-key-0123456789abcdef"
IBAN = "GB82 WEST 1234 5698 7654 32"


def _alice(pg: PgUrls) -> User:
    with psycopg.connect(pg.admin) as admin:
        user_id, tenant_id = admin.execute(
            "SELECT id, tenant_id FROM users WHERE email = 'alice@aldermoor.example.com'"
        ).fetchone()
    return User(id=str(user_id), tenant_id=str(tenant_id), email="alice@aldermoor.example.com",
                roles=["employee"], permissions=[])  # fmt: skip


def _result() -> AnswerResult:
    chunk = Chunk(id="expense-payees:1:0", doc_id="expense-payees", source="p.md", page=1, text="t")
    return AnswerResult(
        status="answered",
        answer=f"Pay to {IBAN} [expense-payees:1].",
        citations=[Citation(doc_id="expense-payees", page=1)],
        retrieved=[ScoredChunk(chunk=chunk, score=0.91)],
        prompt_version="answer_v1",
        verdicts=[
            GuardVerdict(guard="input", decision="ALLOW", score=0.01, reason="classifier"),
            GuardVerdict(guard="context", decision="MASK", reason="expense-payees:1:0: IBAN"),
            GuardVerdict(guard="grounding", decision="PASS"),
        ],
        timings={"retrieve": 120.5, "generate": 900.0},
    )


def _rows(pg: PgUrls, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(pg.admin) as admin:
        return admin.execute(sql, params).fetchall()


def test_a_request_is_recorded_at_the_start_without_its_raw_text(pg: PgUrls) -> None:
    alice, request_id = _alice(pg), str(uuid.uuid4())
    question = f"My IBAN is {IBAN}, how do I claim expenses?"
    with connect(pg.app, autocommit=True) as conn:
        AuditRecorder(conn, KEY).start(request_id, alice, question)

    [(status, query_hmac, query_redacted)] = _rows(
        pg, "SELECT status, query_hmac, query_redacted FROM requests WHERE id = %s", (request_id,)
    )
    assert status == "started"
    tenant_key = hmac.new(KEY.encode(), f"tenant:{alice.tenant_id}".encode(), hashlib.sha256)
    assert (
        query_hmac == hmac.new(tenant_key.digest(), question.encode(), hashlib.sha256).hexdigest()
    )
    assert query_redacted == "My IBAN is [IBAN], how do I claim expenses?"
    assert _rows(pg, "SELECT stage, decision FROM audit_events") == [("request", "START")]


def test_finishing_records_status_sources_every_decision_and_timings(pg: PgUrls) -> None:
    alice, request_id = _alice(pg), str(uuid.uuid4())
    with connect(pg.app, autocommit=True) as conn:
        recorder = AuditRecorder(conn, KEY)
        recorder.start(request_id, alice, "How do I get reimbursed?")
        recorder.finish(request_id, alice, _result(), latency_ms=1234, model="groq:test")
        chain = verify(conn, alice.tenant_id)

    [(status, answer, latency, model, prompt)] = _rows(
        pg,
        "SELECT status, answer_redacted, latency_ms, model, prompt_version FROM requests",
    )
    assert (status, latency, model, prompt) == ("answered", 1234, "groq:test", "answer_v1")
    assert IBAN not in answer and "[IBAN]" in answer
    assert _rows(pg, "SELECT rank, chunk_ref, score FROM request_sources") == [
        (1, "expense-payees:1:0", 0.91)
    ]
    events = _rows(pg, "SELECT seq, stage, decision FROM audit_events ORDER BY seq")
    assert [(s, d) for _, s, d in events] == [
        ("request", "START"),
        ("input_guard", "ALLOW"),
        ("retrieve", "OK"),
        ("context_guard", "MASK"),
        ("grounding_judge", "PASS"),
        ("finish", "ANSWERED"),
    ]
    [(details,)] = _rows(pg, "SELECT details FROM audit_events WHERE stage = 'finish'")
    assert details["timings_ms"] == {"retrieve": 120.5, "generate": 900.0}
    assert chain.ok and chain.rows_checked == 6


def test_a_failure_is_recorded_as_an_error(pg: PgUrls) -> None:
    alice, request_id = _alice(pg), str(uuid.uuid4())
    with connect(pg.app, autocommit=True) as conn:
        recorder = AuditRecorder(conn, KEY)
        recorder.start(request_id, alice, "How much leave?")
        recorder.fail(request_id, alice, "GuardUnavailable", latency_ms=50)

    assert _rows(pg, "SELECT status FROM requests") == [("error",)]
    [(decision, details)] = _rows(
        pg, "SELECT decision, details FROM audit_events WHERE stage = 'finish'"
    )
    assert (decision, details) == ("ERROR", {"error": "GuardUnavailable"})


def test_a_failure_keeps_the_decisions_made_before_it(pg: PgUrls) -> None:
    # Tester v0.6.0 T-2: a rate-limited request used to keep only START and ERROR.
    alice, request_id, done = _alice(pg), str(uuid.uuid4()), _result()
    timings = {"retrieve": 120.5, "generate": 30000.0}
    progress = Progress(
        failed_step="generate",
        verdicts=done.verdicts[:2],
        retrieved=done.retrieved,
        timings=timings,
    )
    with connect(pg.app, autocommit=True) as conn:
        recorder = AuditRecorder(conn, KEY)
        recorder.start(request_id, alice, "How much leave?")
        recorder.fail(request_id, alice, "RateLimitError", latency_ms=30100, progress=progress)

    events = _rows(pg, "SELECT stage, decision, details FROM audit_events ORDER BY seq")
    assert [(stage, decision) for stage, decision, _ in events] == [
        ("request", "START"), ("input_guard", "ALLOW"), ("retrieve", "OK"),
        ("context_guard", "MASK"), ("finish", "ERROR"),
    ]  # fmt: skip
    assert events[-1][2] == {
        "error": "RateLimitError", "failed_step": "generate", "timings_ms": timings,
    }  # fmt: skip
    assert _rows(pg, "SELECT chunk_ref FROM request_sources") == [("expense-payees:1:0",)]
    assert verify(psycopg.connect(pg.admin), alice.tenant_id).ok


def test_nothing_raw_is_stored_anywhere(pg: PgUrls) -> None:
    alice, request_id = _alice(pg), str(uuid.uuid4())
    secret_question = f"Key sk-abcdefghijklmnopqrstuvwxyz123 and IBAN {IBAN}?"
    with connect(pg.app, autocommit=True) as conn:
        recorder = AuditRecorder(conn, KEY)
        recorder.start(request_id, alice, secret_question)
        recorder.finish(request_id, alice, _result(), latency_ms=10, model="m")

    everything = (
        str(_rows(pg, "SELECT * FROM requests"))
        + str(_rows(pg, "SELECT * FROM audit_events"))
        + str(_rows(pg, "SELECT * FROM request_sources"))
    )
    assert IBAN not in everything and "GB82" not in everything
    assert "sk-abcdefghij" not in everything


def test_the_same_question_has_unrelated_fingerprints_in_two_tenants() -> None:
    # Tester v0.6.0 T-7 / ISS-058: one global key let anyone with the database link tenants.
    recorder = AuditRecorder(None, KEY)
    question = "How many days of annual leave do I get?"
    aldermoor, northgate = (
        recorder.query_hmac(t, question) for t in ("t-aldermoor", "t-northgate")
    )
    assert aldermoor != northgate
    assert recorder.query_hmac("t-aldermoor", question) == aldermoor  # still findable in a tenant
