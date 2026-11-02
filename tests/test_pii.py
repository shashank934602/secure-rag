"""S2 (ISS-043): detecting and masking sensitive personal data — and leaving work contacts alone."""

import pytest

from app.guards.pii import detect, mask


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Pay to GB82 WEST 1234 5698 7654 32 please", "IBAN"),
        ("IBAN GB82WEST12345698765432", "IBAN"),
        ("sort code 40-12-34, account 31926819", "UK_BANK_ACCOUNT"),
        ("NI number JM 49 28 37 A", "UK_NINO"),
        ("card 4111 1111 1111 1111 expires", "CREDIT_CARD"),
        ("mobile 07700 900123", "UK_MOBILE"),
        ("mobile +44 7700 900123", "UK_MOBILE"),
        ("home email d.mills.home@gmail.com", "PERSONAL_EMAIL"),
    ],
)
def test_each_sensitive_type_is_detected(text: str, kind: str) -> None:
    assert [m.kind for m in detect(text)] == [kind]


@pytest.mark.parametrize(
    "text",
    [
        "IBAN GB00WEST12345698765432",  # wrong checksum: not a real IBAN
        "card 4111 1111 1111 1112",  # fails the Luhn check
        "Call the IT Service Desk on 555-0150.",  # a work desk phone
        "Email security@aldermoor.example.com or hannah.brooks@aldermoor.example.com.",
        "Invoice AF-PRC-2025-014 for £4,200 on 2026-10-31.",  # references, money, dates
        "Employee ID AF-10031.",
    ],
)
def test_ordinary_business_data_is_left_alone(text: str) -> None:
    assert detect(text) == []


def test_mask_replaces_values_and_reports_the_types() -> None:
    text = "Dave: GB82 WEST 1234 5698 7654 32, NI JM 49 28 37 A, tel 07700 900123, desk 555-0150."

    masked, kinds = mask(text)

    assert masked == "Dave: [IBAN], NI [UK_NINO], tel [UK_MOBILE], desk 555-0150."
    assert kinds == ["IBAN", "UK_MOBILE", "UK_NINO"]


def test_text_without_sensitive_data_is_unchanged() -> None:
    text = "Full-time employees receive 25 days of paid annual leave."
    assert mask(text) == (text, [])
