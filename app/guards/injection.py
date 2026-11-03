"""Prompt-injection detection (spec 05 D1–D2): pattern rules, plus a local classifier.

Two independent detectors, because each misses different things: rules are exact and cheap but
only know phrasings someone wrote down; the classifier generalises but over-reacts to some
ordinary wording. Either one blocks. A detector that fails raises GuardUnavailable, and the
caller refuses (fail closed, Invariant 4): a guard is never skipped.
"""

import re
from typing import Protocol

from app.domain import GuardVerdict

CLASSIFIER_MODEL = "protectai/deberta-v3-base-prompt-injection-v2"

# Known attack phrasings. Kept narrow on purpose: each one is tested against ordinary questions
# ("What if I ignore a safety warning?" must pass), and the classifier covers the rest.
_RULES = {
    "ignore-instructions": r"\bignore\b.{0,40}"
    r"\b(instructions?|rules|prompts?|guidelines|directions)\b",
    "override-instructions": r"\b(disregard|override|bypass)\b.{0,40}"
    r"\b(instructions?|rules|prompts?|guidelines|restrictions|guardrails?)\b",
    "prompt-extraction": r"\b(system|hidden|initial|secret)\s+(prompt|instructions)\b",
    "role-change": r"\byou\s+are\s+now\b|\bdeveloper\s+mode\b|\bjailbr(oken|eak)\b|\bDAN\b",
    "data-dump": r"\b(list|show|print|dump|reveal|output)\b.{0,40}\b(every|all)\b.{0,30}"
    r"\b(documents?|files|chunks)\b.{0,40}\b(you\s+(can\s+)?(see|access|have)|in\s+(your|the)\s+"
    r"(context|database|index|system))",
    "cross-tenant": r"\b(documents?|data|files)\b.{0,40}\b(other|another|every)\s+"
    r"(compan(y|ies)|tenants?|organi[sz]ations?)\b",
    "exfiltration": r"\b(include|insert|add|append|embed|render)\b.{0,40}"
    r"\b(link|url|image|img|markdown|html)\b",
}
_COMPILED = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in _RULES.items()}


class GuardUnavailable(Exception):
    """A guard couldn't run (model missing, error, timeout). The request must be refused."""


class InjectionClassifier(Protocol):
    def score(self, text: str) -> float:
        """Probability (0–1) that the text is an injection attempt."""
        ...


def rule_match(text: str) -> str | None:
    """The name of the first attack rule the text matches, or None."""
    return next((name for name, rx in _COMPILED.items() if rx.search(text)), None)


class DebertaInjectionClassifier:
    """`protectai/deberta-v3-base-prompt-injection-v2`, run locally (CPU or Apple MPS).

    The model reads at most 512 tokens, so long texts (document chunks) are scored in
    overlapping windows and the highest window wins. Loaded on first use (~740 MB download once).
    """

    def __init__(self, model_name: str = CLASSIFIER_MODEL, window: int = 500, overlap: int = 50):
        self.model_name, self.window, self.overlap = model_name, window, overlap
        self._pipeline = None

    def load(self) -> None:
        """Load the model now (the API does this at start-up, so no user waits for it)."""
        if self._pipeline is None:
            from transformers import pipeline  # heavy import: only when used

            self._pipeline = pipeline("text-classification", model=self.model_name)

    def score(self, text: str) -> float:
        self.load()
        windows = self._windows(text)
        results = self._pipeline(windows, truncation=True, max_length=512)
        return max(r["score"] if r["label"] == "INJECTION" else 1 - r["score"] for r in results)

    def _windows(self, text: str) -> list[str]:
        tokenizer = self._pipeline.tokenizer
        ids = tokenizer(text, add_special_tokens=False)["input_ids"]
        if len(ids) <= self.window:
            return [text]
        step = self.window - self.overlap
        return [tokenizer.decode(ids[i : i + self.window]) for i in range(0, len(ids), step)]


class InputGuard:
    """Checks the question before anything else runs; BLOCK means the request is refused."""

    def __init__(self, classifier: InjectionClassifier, threshold: float = 0.5) -> None:
        self.classifier, self.threshold = classifier, threshold

    def check(self, question: str) -> GuardVerdict:
        rule = rule_match(question)
        if rule:  # cheap and exact: no need to run the model
            return GuardVerdict(guard="input", decision="BLOCK", score=1.0, reason=f"rule:{rule}")
        try:
            score = self.classifier.score(question)
        except Exception as error:
            raise GuardUnavailable(f"input guard: {type(error).__name__}") from error
        decision = "BLOCK" if score >= self.threshold else "ALLOW"
        return GuardVerdict(guard="input", decision=decision, score=round(score, 4),
                            reason="classifier")  # fmt: skip
