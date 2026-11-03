"""Recording requests in the audit trail (spec 06 D4–D6, ISS-051).

    start()   when a question arrives: the request record (status 'started') + a START event
    finish()  when it ends, in ONE transaction: status, redacted answer, sources, one event per
              decision, and the per-step timings
    fail()    when it errors: status 'error' + an ERROR event

Nothing raw is stored (Invariant 5): the question is kept as an HMAC (a keyed hash, so the same
question can be found again without storing it) and as redacted text; every stored text passes
through `redact`. If recording fails, the caller refuses the request (fail closed, D6).
"""

import hashlib
import hmac

import psycopg
from psycopg_pool import ConnectionPool

from app.audit.log import append_in_transaction
from app.db import borrow, tenant_scope
from app.domain import AnswerResult, User
from app.guards.output import redact

# Guard names in verdicts → the graph stage they come from (the audit's `stage` column).
_STAGES = {"input": "input_guard", "context": "context_guard", "output": "output_checks",
           "grounding": "grounding_judge"}  # fmt: skip


class AuditRecorder:
    def __init__(self, db: psycopg.Connection | ConnectionPool, hmac_key: str) -> None:
        if not hmac_key:
            raise ValueError("AUDIT_HMAC_KEY is not set (see .env.example)")
        self.db, self._key = db, hmac_key.encode()

    def query_hmac(self, question: str) -> str:
        return hmac.new(self._key, question.encode(), hashlib.sha256).hexdigest()

    def start(self, request_id: str, user: User, question: str) -> None:
        with borrow(self.db) as conn, tenant_scope(conn, user.tenant_id):
            conn.execute(
                """INSERT INTO requests (id, tenant_id, user_id, query_hmac, query_redacted)
                   VALUES (%s, %s, %s, %s, %s)""",
                (request_id, user.tenant_id, user.id, self.query_hmac(question), redact(question)),
            )
            append_in_transaction(
                conn, user.tenant_id, [_event(request_id, user, "request", "START")]
            )

    def finish(
        self,
        request_id: str,
        user: User,
        result: AnswerResult,
        *,
        latency_ms: int,
        model: str,
        judge_prompt_version: str | None = None,
    ) -> None:
        # In flow order: the input guard, retrieval, then every later decision, then the outcome.
        decisions = [
            _event(request_id, user, _STAGES.get(v.guard, v.guard), v.decision, score=v.score,
                   details={"reason": redact(v.reason)} if v.reason else {})
            for v in result.verdicts
        ]  # fmt: skip
        first = [e for e in decisions if e["stage"] == "input_guard"]
        later = [e for e in decisions if e["stage"] != "input_guard"]
        retrieve = [_retrieve_event(request_id, user, result)] if result.retrieved else []
        outcome = _event(request_id, user, "finish", result.status.upper(),
                         details={"timings_ms": result.timings})  # fmt: skip
        events = [*first, *retrieve, *later, outcome]

        with borrow(self.db) as conn, tenant_scope(conn, user.tenant_id):  # all or nothing
            conn.execute(
                """UPDATE requests SET status = %s, answer_redacted = %s, latency_ms = %s,
                          model = %s, prompt_version = %s, judge_prompt_version = %s,
                          finished_at = now()
                   WHERE id = %s""",
                (result.status, redact(result.answer), latency_ms, model, result.prompt_version,
                 judge_prompt_version, request_id),
            )  # fmt: skip
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO request_sources (request_id, tenant_id, rank, chunk_ref, score)
                       VALUES (%s, %s, %s, %s, %s)""",
                    [(request_id, user.tenant_id, rank, hit.chunk.id, hit.score)
                     for rank, hit in enumerate(result.retrieved, start=1)],
                )  # fmt: skip
            append_in_transaction(conn, user.tenant_id, events)

    def fail(self, request_id: str, user: User, error: str, *, latency_ms: int) -> None:
        with borrow(self.db) as conn, tenant_scope(conn, user.tenant_id):
            conn.execute(
                "UPDATE requests SET status = 'error', latency_ms = %s, finished_at = now() "
                "WHERE id = %s",
                (latency_ms, request_id),
            )
            append_in_transaction(
                conn, user.tenant_id,
                [_event(request_id, user, "finish", "ERROR", details={"error": error})],
            )  # fmt: skip

    def acl_changed(self, conn: psycopg.Connection, user: User, change: dict) -> None:
        """Inside the ACL change's own transaction (atomic with the change)."""
        details = {
            "doc_id": change["doc_id"],
            "from": change["previous_roles"],
            "to": change["allowed_roles"],
            "chunks_updated": change["chunks_updated"],
        }
        append_in_transaction(
            conn, user.tenant_id, [_event(None, user, "acl_change", "ALLOW", details=details)]
        )

    def acl_refused(self, user: User, doc_id: str, status: int, reason: str) -> None:
        details = {"doc_id": doc_id, "status": status, "reason": redact(reason)}
        with borrow(self.db) as conn, tenant_scope(conn, user.tenant_id):
            append_in_transaction(
                conn, user.tenant_id, [_event(None, user, "acl_change", "BLOCK", details=details)]
            )


class NullRecorder:
    """Records nothing. For offline unit tests and the quality eval only; the API's default is
    the real AuditRecorder, and it refuses to start without AUDIT_HMAC_KEY."""

    def start(self, *args, **kwargs) -> None: ...
    def finish(self, *args, **kwargs) -> None: ...
    def fail(self, *args, **kwargs) -> None: ...
    def acl_changed(self, *args, **kwargs) -> None: ...
    def acl_refused(self, *args, **kwargs) -> None: ...


def _event(request_id, user: User, stage: str, decision: str, score=None, details=None) -> dict:
    return {"request_id": request_id, "actor_id": user.id, "stage": stage, "decision": decision,
            "score": score, "details": details or {}}  # fmt: skip


def _retrieve_event(request_id, user: User, result: AnswerResult) -> dict:
    refs = [hit.chunk.id for hit in result.retrieved]
    return _event(request_id, user, "retrieve", "OK", details={"chunks": refs})
