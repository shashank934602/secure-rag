"""The grounding judge (spec 05 D6–D7): is every claim in the answer supported by its sources?

The citation check only proves an answer *points at* retrieved pages; it can't tell whether those
pages say what the answer claims ("The CEO earns £200,000 [expense-policy:1]" passed it). The
judge reads the cited chunks and the answer and lists unsupported claims. It is a model from a
**different family** than the generator, which would tend to approve text in its own style.
Any error or unreadable verdict raises GuardUnavailable: the request fails closed.
"""

import json
import re
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.domain import Citation, GuardVerdict, ScoredChunk
from app.guards.injection import GuardUnavailable

JUDGE_PROMPT_VERSION = "judge_v1"
_PROMPT = (
    Path(__file__).resolve().parent.parent / "prompts" / f"{JUDGE_PROMPT_VERSION}.md"
).read_text(encoding="utf-8")
_JSON = re.compile(r"\{.*\}", re.DOTALL)


class GroundingJudge:
    def __init__(self, model: BaseChatModel) -> None:
        self.model = model

    def check(
        self, answer: str, citations: list[Citation], retrieved: list[ScoredChunk]
    ) -> GuardVerdict:
        cited = {(c.doc_id, c.page) for c in citations}
        documents = "\n\n".join(
            f'<document id="{r.chunk.doc_id}:{r.chunk.page}">\n{r.chunk.text}\n</document>'
            for r in retrieved
            if (r.chunk.doc_id, r.chunk.page) in cited
        )
        messages = [
            SystemMessage(_PROMPT),
            HumanMessage(f"{documents}\n\n<answer>\n{answer}\n</answer>"),
        ]
        try:
            reply = self.model.invoke(messages).text
        except Exception as error:
            raise GuardUnavailable(f"grounding judge: {type(error).__name__}") from error

        verdict = _parse(reply)
        if verdict is None:
            raise GuardUnavailable("grounding judge: unreadable verdict")
        grounded, unsupported = verdict
        if grounded:
            return GuardVerdict(guard="grounding", decision="PASS")
        return GuardVerdict(guard="grounding", decision="FAIL", reason="; ".join(unsupported))


def _parse(reply: str) -> tuple[bool, list[str]] | None:
    match = _JSON.search(reply or "")
    if not match:
        return None
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    grounded, unsupported = data.get("grounded"), data.get("unsupported", [])
    if not isinstance(grounded, bool) or not isinstance(unsupported, list):
        return None
    return grounded, [str(claim) for claim in unsupported]
