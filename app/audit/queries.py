"""What an auditor can read (spec 06 D7, ISS-052). Every read runs in the auditor's tenant scope
(row-level security: another company's requests don't exist for them) and is itself appended to
the audit trail, in the same transaction, as an `audit_read` event. Refused attempts (403: not an
auditor; 404: no such request in this tenant) are recorded too, as `audit_read` BLOCK: who tried
to look matters as much as who looked (tester v0.6.0 T-4).
"""

from datetime import datetime

import psycopg
from psycopg_pool import ConnectionPool

from app.audit.log import append_in_transaction, verify
from app.db import borrow, tenant_scope
from app.domain import User

AUDITOR = "auditor"
_REQUEST_FIELDS = ("id", "user_id", "status", "query_hmac", "query_redacted", "answer_redacted",
                   "model", "prompt_version", "judge_prompt_version", "latency_ms", "created_at",
                   "finished_at")  # fmt: skip


class AuditAccessError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


def _require_auditor(db: psycopg.Connection | ConnectionPool, user: User, details: dict) -> None:
    if AUDITOR not in user.permissions:
        with borrow(db) as conn, tenant_scope(conn, user.tenant_id):  # the attempt is evidence
            refused = _read_event(user, {**details, "status": 403}, decision="BLOCK")
            append_in_transaction(conn, user.tenant_id, [refused])
        raise AuditAccessError(403, "Not allowed to read the audit trail")


def _read_event(user: User, details: dict, decision: str = "ALLOW") -> dict:
    return {"request_id": None, "actor_id": user.id, "stage": "audit_read", "decision": decision,
            "score": None, "details": details}  # fmt: skip


def _plain(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None and not isinstance(value, int | float | str) else value


def get_request(db: psycopg.Connection | ConnectionPool, user: User, request_id: str) -> dict:
    _require_auditor(db, user, {"request_id": request_id})
    with borrow(db) as conn, tenant_scope(conn, user.tenant_id):
        row = conn.execute(
            f"SELECT {', '.join(_REQUEST_FIELDS)} FROM requests WHERE id = %s", (request_id,)
        ).fetchone()
        if row is None:  # doesn't exist, or another tenant's (RLS): record the probe, then 404
            probe = _read_event(user, {"request_id": request_id, "status": 404}, "BLOCK")
            append_in_transaction(conn, user.tenant_id, [probe])
        else:
            sources = conn.execute(
                "SELECT rank, chunk_ref, score FROM request_sources WHERE request_id = %s "
                "ORDER BY rank",
                (request_id,),
            ).fetchall()
            events = conn.execute(
                """SELECT seq, stage, decision, score, details, actor_id, created_at
                   FROM audit_events WHERE request_id = %s ORDER BY seq""",
                (request_id,),
            ).fetchall()
            read = _read_event(user, {"request_id": request_id})
            append_in_transaction(conn, user.tenant_id, [read])
    if row is None:
        raise AuditAccessError(404, "Request not found")
    return {
        "request": {k: _plain(v) for k, v in zip(_REQUEST_FIELDS, row, strict=True)},
        "sources": [{"rank": r, "chunk_ref": ref, "score": s} for r, ref, s in sources],
        "events": [
            {
                "seq": seq,
                "stage": stage,
                "decision": decision,
                "score": score,
                "details": details,
                "actor_id": _plain(actor),
                "created_at": _plain(created),
            }
            for seq, stage, decision, score, details, actor, created in events
        ],  # fmt: skip
    }


def list_requests(
    db: psycopg.Connection | ConnectionPool,
    user: User,
    *,
    status: str | None = None,
    user_id: str | None = None,
    since: datetime | None = None,
    limit: int = 50,
) -> list[dict]:
    _require_auditor(db, user, {"search": {"status": status}})
    conditions, params = ["TRUE"], []
    for column, value in (("status", status), ("user_id", user_id)):
        if value is not None:
            conditions.append(f"{column} = %s")
            params.append(value)
    if since is not None:
        conditions.append("created_at >= %s")
        params.append(since)
    with borrow(db) as conn, tenant_scope(conn, user.tenant_id):
        rows = conn.execute(
            f"""SELECT id, user_id, status, query_redacted, latency_ms, created_at FROM requests
                WHERE {" AND ".join(conditions)} ORDER BY created_at DESC LIMIT %s""",
            (*params, limit),
        ).fetchall()
        filters = {"status": status, "user_id": user_id, "since": _plain(since), "limit": limit}
        append_in_transaction(conn, user.tenant_id, [_read_event(user, {"search": filters})])
    keys = ("id", "user_id", "status", "query_redacted", "latency_ms", "created_at")
    return [{k: _plain(v) for k, v in zip(keys, row, strict=True)} for row in rows]


def verify_tenant(db: psycopg.Connection | ConnectionPool, user: User) -> dict:
    _require_auditor(db, user, {"verify": None})
    with borrow(db) as conn:
        result = verify(conn, user.tenant_id)
        with tenant_scope(conn, user.tenant_id):  # the check is recorded after it ran
            append_in_transaction(
                conn, user.tenant_id, [_read_event(user, {"verify": {"ok": result.ok}})]
            )
    return {"ok": result.ok, "rows_checked": result.rows_checked,
            "first_broken": result.first_broken, "reason": result.reason}  # fmt: skip
