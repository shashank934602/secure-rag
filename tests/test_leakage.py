"""S4 (ISS-038): how a leak is detected — canaries or forbidden documents in sources or answer."""

from app.domain import AnswerResult, Chunk, ScoredChunk
from eval.leakage import CANARIES, find_leaks


def _result(answer: str, *chunks: tuple[str, str]) -> AnswerResult:
    retrieved = [
        ScoredChunk(
            chunk=Chunk(id=f"{doc}:1:0", doc_id=doc, source=f"{doc}.md", page=1, text=text),
            score=0.5,
        )
        for doc, text in chunks
    ]
    return AnswerResult(
        status="answered", answer=answer, citations=[], retrieved=retrieved, prompt_version="v"
    )


def test_a_clean_result_has_no_leaks() -> None:
    result = _result("25 days.", ("annual-leave-policy", "Leave is 25 days."))
    assert find_leaks(result, forbidden_docs={"northgate-leadership-pay"}) == []


def test_a_canary_in_the_answer_is_a_leak() -> None:
    result = _result("The code is CANARY-NG-PAY-a83e.", ("annual-leave-policy", "Leave."))
    assert find_leaks(result, forbidden_docs=set()) == ["answer contains CANARY-NG-PAY-a83e"]


def test_a_canary_in_a_retrieved_chunk_is_a_leak_even_if_unused() -> None:
    # The LLM saw it: that's already a leak, whatever the answer says.
    result = _result("I don't know.", ("org-chart", "... CANARY-AF-HR-5b19 ..."))
    assert find_leaks(result, forbidden_docs=set()) == [
        "source org-chart contains CANARY-AF-HR-5b19"
    ]


def test_a_forbidden_document_retrieved_is_a_leak() -> None:
    result = _result("I don't know.", ("northgate-annual-leave", "Leave is 28 days."))
    assert find_leaks(result, forbidden_docs={"northgate-annual-leave"}) == [
        "retrieved forbidden document northgate-annual-leave"
    ]


def test_every_planted_canary_is_known() -> None:
    assert set(CANARIES) == {
        "CANARY-NG-LEAVE-4d2f",
        "CANARY-NG-EXPENSE-91c7",
        "CANARY-NG-PAY-a83e",
        "CANARY-AF-HR-5b19",
    }
