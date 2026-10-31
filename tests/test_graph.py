"""S3 (ISS-032): the answering flow as a LangGraph state machine: routes and one retry."""

from app.answering.answer import NO_ANSWER, RETRY_NOTE, Answerer
from app.domain import Chunk
from app.retrieval.search import ChunkIndex
from tests.fakes import KeywordEmbeddings, ScriptedChatModel, ScriptedReranker

VOCAB = ["leave", "hotel"]
CHUNKS = [
    Chunk(id="leave:1:0", doc_id="leave", source="leave.md", page=1, text="Leave is 25 days."),
    Chunk(id="hotel:1:0", doc_id="hotel", source="hotel.md", page=1, text="Hotel limit £190."),
]


def _answerer(*responses: str, reranker=None, threshold: float = 0.0) -> Answerer:
    return Answerer(
        index=ChunkIndex(CHUNKS, KeywordEmbeddings(VOCAB)),
        chat_model=ScriptedChatModel(responses=list(responses)),
        top_k=2,
        reranker=reranker,
        threshold=threshold,
    )


def test_valid_citations_are_answered_first_time() -> None:
    a = _answerer("Leave is 25 days [leave:1].")

    result = a.answer("How much leave?")

    assert (result.status, len(a.chat_model.calls)) == ("answered", 1)


def test_invalid_citations_get_one_retry_with_a_correction_note() -> None:
    a = _answerer("Leave is 25 days.", "Leave is 25 days [leave:1].")

    result = a.answer("How much leave?")

    assert result.status == "answered"
    assert result.answer == "Leave is 25 days [leave:1]."
    retry_messages = a.chat_model.calls[1]
    assert retry_messages[-2].content == "Leave is 25 days."  # the model sees its first reply
    assert retry_messages[-1].content == RETRY_NOTE  # and why it was rejected


def test_invalid_twice_is_a_no_answer_after_exactly_two_calls() -> None:
    a = _answerer("Leave is 25 days [made-up:9].", "Still [made-up:9].")

    assert a.answer("How much leave?").status == "no_answer"
    assert len(a.chat_model.calls) == 2


def test_the_model_saying_no_answer_is_final_and_not_retried() -> None:
    a = _answerer(NO_ANSWER)

    assert a.answer("What is the CEO's salary?").status == "no_answer"
    assert len(a.chat_model.calls) == 1


def test_below_the_threshold_the_graph_skips_generation() -> None:
    a = _answerer("never used", reranker=ScriptedReranker({"leave:1:0": 0.1}), threshold=0.5)

    assert a.answer("How much leave?").status == "no_answer"
    assert a.chat_model.calls == []


def test_the_graph_has_the_designed_steps() -> None:
    nodes = set(_answerer().graph.get_graph().nodes)
    assert {"retrieve", "generate", "check_citations", "no_answer"} <= nodes
