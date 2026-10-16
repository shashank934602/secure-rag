"""Warm-up exercise 1 (ISS-015): make the citation parser accept the formats real models use.

The first four strings below are the model's *actual* replies from the first real run (2026-10-15).
Each one was a correct answer that our parser threw away.

Run only these tests:   uv run pytest tests/test_citations.py -v
"""

import pytest

from app.answering.citations import parse_citations
from app.domain import Citation

# --- Real replies from gpt-oss-120b, verbatim ------------------------------------------------

REAL_G01 = (
    "Full‑time employees are entitled to **25 days of paid annual leave** each leave year "
    "(in addition to the 8 UK bank holidays)【annual-leave-policy:1】."
)
REAL_G03 = (
    "The policy sets the maximum nightly hotel rate (room only) for London at "
    "**£190 per night**【expense-policy:1:1】."
)
REAL_G04 = (
    "Aldermoor must pay undisputed SwiftParts invoices within 45 days of the invoice date"
    "【vendor-contract-swiftparts:2】."
)
REAL_G05 = (
    "You must report a lost work laptop **within 1 hour** of noticing it. Report it to the IT "
    "Service Desk by calling **555‑0150** or by emailing **security@aldermoor.example.com**"
    "【it-security-policy:1】."
)


# --- Already working: keep these green ----------------------------------------------------


def test_square_bracket_citation() -> None:
    assert parse_citations("25 days [annual-leave-policy:1].") == [
        Citation(doc_id="annual-leave-policy", page=1)
    ]


def test_several_ids_in_one_bracket() -> None:
    assert parse_citations("See [leave:1, expense:2].") == [
        Citation(doc_id="leave", page=1),
        Citation(doc_id="expense", page=2),
    ]


def test_ordinary_brackets_are_not_citations() -> None:
    assert parse_citations("Fees [excluding VAT] apply [see section 4].") == []


# --- Your exercise: make these pass ------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (REAL_G01, Citation(doc_id="annual-leave-policy", page=1)),
        (REAL_G04, Citation(doc_id="vendor-contract-swiftparts", page=2)),
        (REAL_G05, Citation(doc_id="it-security-policy", page=1)),
    ],
)
def test_full_width_brackets_from_real_replies(reply: str, expected: Citation) -> None:
    assert parse_citations(reply) == [expected]


def test_chunk_id_citation_counts_as_its_page() -> None:
    # "doc_id:page:index" is a chunk id; the citation is still that document and page.
    assert parse_citations("190 per night [expense-policy:1:1].") == [
        Citation(doc_id="expense-policy", page=1)
    ]


def test_full_width_bracket_with_chunk_id_from_real_reply() -> None:
    assert parse_citations(REAL_G03) == [Citation(doc_id="expense-policy", page=1)]


def test_mixed_formats_are_deduplicated_in_order() -> None:
    text = "A [leave:1]. B 【expense:2】. C [leave:1:0]. D 【expense:2:1】."
    assert parse_citations(text) == [
        Citation(doc_id="leave", page=1),
        Citation(doc_id="expense", page=2),
    ]


def test_full_width_ordinary_text_is_not_a_citation() -> None:
    assert parse_citations("Note【see the appendix】.") == []
