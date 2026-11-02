"""Sensitive personal data (spec 05 D3–D4; ADR-0004): detect at ingest, mask at query time.

Only an allow-list of *sensitive identifiers* is masked: bank details, National Insurance
numbers, card numbers, personal mobiles, personal (consumer) email addresses. Work emails and
desk phones are directory information employees are meant to use, so they are left alone.
Numbers that only *look* right are rejected by their checksums (IBAN mod-97, card Luhn).
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    kind: str
    start: int
    end: int


def _iban_ok(value: str) -> bool:
    compact = value.replace(" ", "").upper()
    rearranged = compact[4:] + compact[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)  # A=10 … Z=35
    return len(compact) >= 15 and int(digits) % 97 == 1


def _luhn_ok(value: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", value)]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


# kind → (pattern, validator). Order matters: earlier kinds win overlapping text.
_PATTERNS: dict[str, tuple[re.Pattern[str], object]] = {
    "IBAN": (re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b"), _iban_ok),
    "UK_BANK_ACCOUNT": (re.compile(r"\b\d{2}-\d{2}-\d{2}\b[^\n\d]{0,25}\b\d{8}\b"), None),
    "UK_NINO": (
        re.compile(r"\b[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z] ?\d{2} ?\d{2} ?\d{2} ?[A-D]\b"),
        None,
    ),
    "CREDIT_CARD": (re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), _luhn_ok),
    "UK_MOBILE": (re.compile(r"(?:\+44 ?7\d{3}|\b07\d{3}) ?\d{3} ?\d{3}\b"), None),
    "PERSONAL_EMAIL": (
        re.compile(
            r"\b[\w.+-]+@(?:gmail|googlemail|outlook|hotmail|live|yahoo|icloud|aol|proton(?:mail)?)"
            r"\.[a-z.]+\b",
            re.IGNORECASE,
        ),
        None,
    ),
}


# Models write narrow or non-breaking spaces and non-breaking hyphens inside numbers. Each maps to
# exactly one plain character, so positions found in the plain copy are valid in the original.
_PLAIN = str.maketrans(
    {c: " " for c in "\u00a0\u2007\u2009\u202f"} | {c: "-" for c in "\u2010\u2011"}
)


def detect(text: str) -> list[Match]:
    """Every sensitive value in the text, in order, without overlaps."""
    found: list[Match] = []
    plain = text.translate(_PLAIN)
    for kind, (pattern, valid) in _PATTERNS.items():
        for m in pattern.finditer(plain):
            if valid and not valid(m.group()):
                continue
            if any(m.start() < f.end and f.start < m.end() for f in found):
                continue  # already covered by an earlier, more specific kind
            found.append(Match(kind, m.start(), m.end()))
    return sorted(found, key=lambda f: f.start)


def mask(text: str) -> tuple[str, list[str]]:
    """The text with each sensitive value replaced by `[KIND]`, and the sorted kinds found."""
    matches = detect(text)
    for m in reversed(matches):  # replace from the end so earlier offsets stay valid
        text = text[: m.start] + f"[{m.kind}]" + text[m.end :]
    return text, sorted({m.kind for m in matches})
