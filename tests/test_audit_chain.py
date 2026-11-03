"""S1 (ISS-050): the hash chain — any edit, deletion, or reordering of past events is detected."""

from datetime import UTC, datetime

from app.audit.chain import GENESIS, canonical, link, verify_chain

T = "11111111-1111-1111-1111-111111111111"


def _event(seq: int, decision: str = "ALLOW", **extra) -> dict:
    return {
        "tenant_id": T,
        "seq": seq,
        "request_id": None,
        "actor_id": None,
        "stage": "input_guard",
        "decision": decision,
        "score": 0.25,
        "details": {"reason": "classifier"},
        "created_at": datetime(2026, 11, 3, 10, 0, seq, tzinfo=UTC).isoformat(),
        **extra,
    }


def _chain(n: int) -> list[dict]:
    rows, prev = [], GENESIS
    for seq in range(1, n + 1):
        row = link(prev, _event(seq))
        rows.append(row)
        prev = row["row_hash"]
    return rows


def test_canonical_form_ignores_key_order() -> None:
    assert canonical({"b": 1, "a": {"y": 2, "x": 1}}) == canonical({"a": {"x": 1, "y": 2}, "b": 1})


def test_each_row_points_at_the_previous_one() -> None:
    rows = _chain(3)
    assert rows[0]["prev_hash"] == GENESIS
    assert rows[1]["prev_hash"] == rows[0]["row_hash"]
    assert len({r["row_hash"] for r in rows}) == 3


def test_an_untouched_chain_verifies() -> None:
    result = verify_chain(_chain(5))
    assert (result.ok, result.rows_checked, result.first_broken) == (True, 5, None)


def test_an_empty_chain_verifies() -> None:
    assert verify_chain([]).ok


def test_editing_any_field_of_a_past_row_is_detected() -> None:
    for field, value in (("decision", "BLOCK"), ("score", 0.99), ("details", {"reason": "x"})):
        rows = _chain(5)
        rows[2] = {**rows[2], field: value}  # someone rewrites history in row 3
        result = verify_chain(rows)
        assert (result.ok, result.first_broken) == (False, 3), field
        assert "content" in result.reason


def test_deleting_a_row_is_detected() -> None:
    rows = _chain(5)
    del rows[1]
    result = verify_chain(rows)
    assert (result.ok, result.first_broken) == (False, 3)
    assert "gap" in result.reason


def test_rehashing_an_edited_row_still_breaks_the_next_link() -> None:
    # A smarter attacker recomputes the edited row's own hash, but can't fix every later row
    # without rewriting the rest of the chain, and the next row still points at the old hash.
    rows = _chain(4)
    forged = link(rows[1]["prev_hash"], {**{k: rows[1][k] for k in _event(2)}, "decision": "BLOCK"})
    rows[1] = forged
    result = verify_chain(rows)
    assert (result.ok, result.first_broken) == (False, 3)
    assert "link" in result.reason
