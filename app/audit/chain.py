"""The hash chain (spec 06 D3, Invariant 6). Pure functions: no database.

Each event's `row_hash` = SHA-256(previous row's hash + "\\n" + the event's content in a fixed
JSON form). Editing any past event changes its hash, which no longer matches what the next event
stored as `prev_hash`; deleting one leaves a gap in `seq`. `verify_chain` recomputes everything
and names the first broken event.
"""

import hashlib
import json
from dataclasses import dataclass

GENESIS = "0" * 64  # the "previous hash" of each tenant's first event

# Exactly the fields that are hashed; the stored hashes themselves are not.
CONTENT_FIELDS = (
    "tenant_id", "seq", "request_id", "actor_id", "stage", "decision", "score", "details",
    "created_at",
)  # fmt: skip


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    rows_checked: int
    first_broken: int | None = None  # the seq of the first event that fails
    reason: str = ""


def canonical(content: dict) -> str:
    """One fixed text form of a dict: sorted keys, no spaces, so the same content → same hash."""
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def row_hash(prev_hash: str, content: dict) -> str:
    fields = {name: content[name] for name in CONTENT_FIELDS}
    return hashlib.sha256(f"{prev_hash}\n{canonical(fields)}".encode()).hexdigest()


def link(prev_hash: str, content: dict) -> dict:
    """The event as stored: its content plus `prev_hash` and its own `row_hash`."""
    return {**content, "prev_hash": prev_hash, "row_hash": row_hash(prev_hash, content)}


def verify_chain(rows: list[dict]) -> VerifyResult:
    """Check one tenant's events, in `seq` order: numbering, links, and content hashes."""
    expected_prev = GENESIS
    for checked, row in enumerate(rows, start=1):
        seq = row["seq"]
        if seq != checked:
            return VerifyResult(False, checked, seq, f"gap: expected seq {checked}, found {seq}")
        if row["prev_hash"] != expected_prev:
            return VerifyResult(False, checked, seq, "broken link: prev_hash doesn't match")
        if row["row_hash"] != row_hash(row["prev_hash"], row):
            return VerifyResult(False, checked, seq, "content changed: row_hash doesn't match")
        expected_prev = row["row_hash"]
    return VerifyResult(True, len(rows))
