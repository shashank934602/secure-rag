"""The eval judge (spec 07 D4, D9, ISS-061): correctness and faithfulness, scored by a pinned model.

The method is RAGAS's (split into claims, check each), in two short prompts we can read:
    correctness   share of the reference answer's claims that the answer contains; 0 if it
                  contradicts the reference
    faithfulness  share of the answer's claims that the retrieved documents support
A score is None when the judge can't be read twice in a row, or when there is nothing to score
(an answer with no claims). The judge is a different model from the grounding judge (D6).
"""

import json
import re
import time
from collections.abc import Callable
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

_PROMPTS = Path(__file__).resolve().parent / "prompts"
CORRECTNESS = "eval_correctness_v1"
FAITHFULNESS = "eval_faithfulness_v1"
_JSON = re.compile(r"\{.*\}", re.DOTALL)


def _prompt(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def parse_claims(reply: str, flag: str) -> tuple[list[bool], dict] | None:
    """The per-claim booleans under `flag` ('present' or 'supported'), and the whole object."""
    match = _JSON.search(reply or "")
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    claims = data.get("claims")
    if not isinstance(claims, list) or not all(
        isinstance(c, dict) and isinstance(c.get(flag), bool) for c in claims
    ):
        return None
    return [c[flag] for c in claims], data


class EvalJudge:
    """Unreadable replies are asked again; provider errors (free-tier rate limits) wait and retry,
    doubling the wait. Still nothing → None, which the report counts as unscored."""

    def __init__(
        self,
        model: BaseChatModel,
        attempts: int = 3,
        wait_s: float = 10.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model, self.attempts, self.wait_s, self.sleep = model, attempts, wait_s, sleep

    def _ask(self, prompt: str, content: str, flag: str) -> tuple[list[bool], dict] | None:
        wait = self.wait_s
        for attempt in range(self.attempts):
            try:
                reply = self.model.invoke([SystemMessage(_prompt(prompt)), HumanMessage(content)])
            except Exception:
                if attempt < self.attempts - 1:
                    self.sleep(wait)
                    wait *= 2
                continue
            parsed = parse_claims(reply.text, flag)
            if parsed is not None:
                return parsed
        return None

    def correctness(self, question: str, reference: str, answer: str) -> float | None:
        content = (f"QUESTION:\n{question}\n\nREFERENCE ANSWER:\n{reference}\n\n"
                   f"ASSISTANT'S ANSWER:\n{answer}")  # fmt: skip
        parsed = self._ask(CORRECTNESS, content, "present")
        if parsed is None:
            return None
        present, data = parsed
        if data.get("contradicts") is True:
            return 0.0
        return sum(present) / len(present) if present else None

    def faithfulness(self, answer: str, documents: list[str]) -> float | None:
        joined = "\n\n".join(f"<document>\n{text}\n</document>" for text in documents)
        parsed = self._ask(FAITHFULNESS, f"DOCUMENTS:\n{joined}\n\nANSWER:\n{answer}", "supported")
        if parsed is None:
            return None
        supported, _ = parsed
        return sum(supported) / len(supported) if supported else None
