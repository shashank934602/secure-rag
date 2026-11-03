"""Writing and verifying the audit trail in Postgres (spec 06 D1–D3).

Appends run inside the tenant's scope (row-level security) and take a per-tenant advisory lock,
so two requests appending at the same moment can't both claim the same `seq` and fork the chain.
"""

from datetime import UTC, datetime

import psycopg
from psycopg.types.json import Jsonb

from app.audit.chain import GENESIS, VerifyResult, link, verify_chain
from app.db import tenant_scope


def append_events(conn: psycopg.Connection, tenant_id: str, events: list[dict]) -> list[int]:
    """Append events (dicts with stage, decision, and optional request_id, actor_id, score,
    details) to the tenant's chain, in one transaction; returns their seq numbers."""
    with tenant_scope(conn, tenant_id):
        return append_in_transaction(conn, tenant_id, events)


def append_in_transaction(
    conn: psycopg.Connection, tenant_id: str, events: list[dict]
) -> list[int]:
    """Same as append_events, for a caller already inside the tenant's transaction."""
    # One lock per tenant, released at commit: appends to the same chain happen one at a time.
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(tenant_id),))
    last = conn.execute(
        "SELECT seq, row_hash FROM audit_events WHERE tenant_id = %s ORDER BY seq DESC LIMIT 1",
        (tenant_id,),
    ).fetchone()
    seq, prev = (last[0], last[1]) if last else (0, GENESIS)
    seqs = []
    for event in events:
        seq += 1
        content = {
            "tenant_id": str(tenant_id),
            "seq": seq,
            "request_id": _str_or_none(event.get("request_id")),
            "actor_id": _str_or_none(event.get("actor_id")),
            "stage": event["stage"],
            "decision": event["decision"],
            "score": event.get("score"),
            "details": event.get("details") or {},
            "created_at": datetime.now(UTC).isoformat(),
        }
        row = link(prev, content)
        conn.execute(
            """INSERT INTO audit_events (tenant_id, seq, request_id, actor_id, stage, decision,
                                         score, details, created_at, prev_hash, row_hash)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                row["tenant_id"], seq, row["request_id"], row["actor_id"], row["stage"],
                row["decision"], row["score"], Jsonb(row["details"]), row["created_at"],
                row["prev_hash"], row["row_hash"],
            ),
        )  # fmt: skip
        prev = row["row_hash"]
        seqs.append(seq)
    return seqs


def verify(conn: psycopg.Connection, tenant_id: str) -> VerifyResult:
    """Recompute the tenant's whole chain from the stored rows."""
    with tenant_scope(conn, tenant_id):
        rows = conn.execute(
            """SELECT tenant_id, seq, request_id, actor_id, stage, decision, score, details,
                      created_at, prev_hash, row_hash
               FROM audit_events WHERE tenant_id = %s ORDER BY seq""",
            (tenant_id,),
        ).fetchall()
    keys = ("tenant_id", "seq", "request_id", "actor_id", "stage", "decision", "score",
            "details", "created_at", "prev_hash", "row_hash")  # fmt: skip
    events = []
    for values in rows:
        row = dict(zip(keys, values, strict=True))
        row["tenant_id"] = str(row["tenant_id"])
        row["request_id"] = _str_or_none(row["request_id"])
        row["actor_id"] = _str_or_none(row["actor_id"])
        row["created_at"] = row["created_at"].astimezone(UTC).isoformat()
        events.append(row)
    return verify_chain(events)


def _str_or_none(value: object) -> str | None:
    return None if value is None else str(value)
