"""S4 (ISS-045): the grounding judge — every claim must be supported by the cited chunks."""

import pytest

from app.domain import Chunk, Citation, ScoredChunk
from app.guards.grounding import GroundingJudge
from app.guards.injection import GuardUnavailable
from tests.fakes import ScriptedChatModel

LEAVE = Chunk(id="leave:1:0", doc_id="leave", source="l.md", page=1, text="Leave is 25 days.")
HOTEL = Chunk(id="hotel:1:0", doc_id="hotel", source="h.md", page=1, text="Hotel limit £190.")
RETRIEVED = [ScoredChunk(chunk=LEAVE, score=0.9), ScoredChunk(chunk=HOTEL, score=0.5)]


def _check(reply: str, answer: str = "Leave is 25 days [leave:1].", cited=("leave", 1)):
    judge_model = ScriptedChatModel(responses=[reply])
    verdict = GroundingJudge(judge_model).check(answer, [Citation(doc_id=cited[0], page=cited[1])],
                                                RETRIEVED)  # fmt: skip
    return verdict, judge_model


def test_a_supported_answer_passes() -> None:
    verdict, _ = _check('{"grounded": true, "unsupported": []}')
    assert (verdict.guard, verdict.decision) == ("grounding", "PASS")


def test_an_unsupported_claim_fails_with_the_claim_as_the_reason() -> None:
    verdict, _ = _check(
        '{"grounded": false, "unsupported": ["The CEO earns £200,000"]}',
        answer="The CEO earns £200,000 [hotel:1].",
        cited=("hotel", 1),
    )
    assert (verdict.decision, verdict.reason) == ("FAIL", "The CEO earns £200,000")


def test_the_judge_sees_only_the_cited_chunks_and_the_answer() -> None:
    _, judge_model = _check('{"grounded": true, "unsupported": []}')
    prompt = judge_model.calls[0][1].content
    assert '<document id="leave:1">' in prompt and "Hotel limit" not in prompt
    assert "<answer>\nLeave is 25 days [leave:1].\n</answer>" in prompt


def test_json_wrapped_in_a_code_block_is_read() -> None:
    verdict, _ = _check('```json\n{"grounded": true, "unsupported": []}\n```')
    assert verdict.decision == "PASS"


@pytest.mark.parametrize("reply", ["Looks fine to me!", '{"grounded": "maybe"}', ""])
def test_an_unreadable_verdict_fails_closed(reply: str) -> None:
    with pytest.raises(GuardUnavailable):
        _check(reply)


def test_a_judge_error_fails_closed() -> None:
    class Down(ScriptedChatModel):
        def _generate(self, *args, **kwargs):
            raise TimeoutError("judge timed out")

    with pytest.raises(GuardUnavailable):
        GroundingJudge(Down(responses=[])).check(
            "Leave is 25 days [leave:1].", [Citation(doc_id="leave", page=1)], RETRIEVED
        )
