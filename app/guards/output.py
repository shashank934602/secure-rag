"""Output checks (spec 05 D5, Invariant 3): what may leave the system in an answer.

Structural, not scored, so they always run:
- links, markdown images, and HTML are removed: a rendered image or link can carry data to an
  attacker's server just by being displayed (exfiltration), so no answer may contain one;
- secrets (API keys, tokens, private keys) are redacted for everyone;
- sensitive personal data is redacted for users without `pii:read` (a second net after the
  context guard, in case the model reproduced something it shouldn't have).
Citations, `[doc:page]` and `【doc:page】`, are left untouched.
"""

import re

from app.domain import AccessScope, GuardVerdict
from app.guards.pii import mask

_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\((?:https?|ftp|mailto|data|javascript):[^)]*\)", re.IGNORECASE)
_HTML = re.compile(r"</?[a-zA-Z][^>]*>")
_URL = re.compile(r"\b(?:https?|ftp)://[^\s<>\]\)]+|\bwww\.[^\s<>\]\)]+", re.IGNORECASE)
_SECRETS = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    r"|\b(?:sk|gsk|pk|rk)[-_][A-Za-z0-9_-]{20,}"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}"
)


def check_output(answer: str, scope: AccessScope | None) -> tuple[str, GuardVerdict]:
    """The answer as it may be shown to this user, and one verdict saying what was changed."""
    changes: list[str] = []
    text = answer

    for name, pattern, replacement in (
        ("image", _IMAGE, ""),
        ("link", _LINK, r"\1"),
        ("html", _HTML, ""),
        ("url", _URL, "[link removed]"),
        ("SECRET", _SECRETS, "[SECRET]"),
    ):
        text, count = pattern.subn(replacement, text)
        if count:
            changes.append(f"{name}×{count}")

    if not (scope and scope.can_read_pii):
        text, kinds = mask(text)
        changes += kinds

    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)
    if not changes:
        reason = "nothing to remove"
        return answer, GuardVerdict(guard="output", decision="PASS", reason=reason)
    return text, GuardVerdict(guard="output", decision="MASK", reason=", ".join(changes))


def redact(text: str) -> str:
    """Text safe to store at rest (Invariant 5): secrets and sensitive personal data masked for
    everyone, whatever the reader's permissions. Used for audit records."""
    return mask(_SECRETS.sub("[SECRET]", text))[0]
