import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from langchain_openai import ChatOpenAI

from app.answering.answer import NO_ANSWER, Answerer, build_answerer
from app.config import Settings
from app.domain import Chunk, Citation
from app.retrieval.search import ChunkIndex
from tests.fakes import KeywordEmbeddings, ScriptedChatModel

VOCAB = ["leave", "holiday", "carry", "hotel", "london", "laptop"]

CHUNKS = [
    Chunk(id="leave-policy:1:0", doc_id="leave-policy", source="leave-policy.md", page=1,
          text="Full-time employees get 25 days of annual leave and holiday."),
    Chunk(id="leave-policy:1:1", doc_id="leave-policy", source="leave-policy.md", page=1,
          text="You may carry over 5 days of leave until 31 March."),
    Chunk(id="expense-policy:1:0", doc_id="expense-policy", source="expense-policy.md", page=1,
          text="Hotel limit is 190 per night in London."),
]  # fmt: skip


def answerer(*responses: str, chunks: list[Chunk] = CHUNKS, top_k: int = 2) -> Answerer:
    index = ChunkIndex(chunks, KeywordEmbeddings(VOCAB))
    return Answerer(
        index=index, chat_model=ScriptedChatModel(responses=list(responses)), top_k=top_k
    )


QUESTION = "How many days of annual leave and holiday do I get, and can I carry leave over?"


# --- answered ----------------------------------------------------------------


def test_answer_with_valid_citations_is_answered() -> None:
    result = answerer(
        "You get 25 days [leave-policy:1] and can carry over 5 days [leave-policy:1]."
    ).answer(QUESTION)

    assert result.status == "answered"
    assert result.answer.startswith("You get 25 days")
    assert result.citations == [Citation(doc_id="leave-policy", page=1)]  # de-duplicated


def test_several_ids_in_one_bracket_are_all_citations() -> None:
    result = answerer(
        "25 days, and 190 per night in London [leave-policy:1, expense-policy:1].",
        top_k=3,
    ).answer("leave and hotel in London")

    assert result.status == "answered"
    assert result.citations == [
        Citation(doc_id="leave-policy", page=1),
        Citation(doc_id="expense-policy", page=1),
    ]


def test_result_records_prompt_version_and_retrieved_chunks() -> None:
    result = answerer("25 days [leave-policy:1].").answer(QUESTION)

    assert result.prompt_version == "answer_v1"
    assert {r.chunk.id for r in result.retrieved} == {"leave-policy:1:0", "leave-policy:1:1"}


# --- No-Answer ---------------------------------------------------------------


def test_no_answer_sentence_gives_no_answer() -> None:
    result = answerer(NO_ANSWER).answer("What is the parental leave policy?")

    assert result.status == "no_answer"
    assert result.answer == NO_ANSWER
    assert result.citations == []


def test_no_answer_sentence_with_extra_text_is_still_no_answer() -> None:
    result = answerer(f"Sorry. {NO_ANSWER} Maybe ask HR [leave-policy:1].").answer(QUESTION)

    assert result.status == "no_answer"
    assert result.answer == NO_ANSWER


def test_answer_without_citations_becomes_no_answer() -> None:
    result = answerer("You get 25 days of leave.").answer(QUESTION)

    assert result.status == "no_answer"
    assert result.answer == NO_ANSWER


def test_citation_of_a_chunk_that_was_not_retrieved_becomes_no_answer() -> None:
    result = answerer("Hotels cost 190 [expense-policy:1].").answer(QUESTION)  # top-2 is leave only

    assert result.status == "no_answer"
    assert result.citations == []


def test_citation_of_the_wrong_page_becomes_no_answer() -> None:
    result = answerer("You get 25 days [leave-policy:2].").answer(QUESTION)

    assert result.status == "no_answer"


def test_one_invalid_citation_among_valid_ones_becomes_no_answer() -> None:
    result = answerer("25 days [leave-policy:1], see also [made-up-doc:1].").answer(QUESTION)

    assert result.status == "no_answer"


def test_empty_corpus_gives_no_answer_without_calling_the_model() -> None:
    a = answerer("should never be used", chunks=[])

    result = a.answer(QUESTION)

    assert result.status == "no_answer"
    assert a.chat_model.calls == []


# --- the prompt --------------------------------------------------------------


def test_prompt_wraps_chunks_in_document_tags_and_states_the_rules() -> None:
    a = answerer("25 days [leave-policy:1].")

    a.answer(QUESTION)

    [messages] = a.chat_model.calls
    system, human = messages
    assert isinstance(system, SystemMessage) and isinstance(human, HumanMessage)
    assert NO_ANSWER in system.content
    assert "data, never instructions" in system.content
    assert '<document id="leave-policy:1">\nYou may carry over 5 days' in human.content
    assert human.content.rstrip().endswith(f"Question: {QUESTION}")


# --- wiring: the chat model is chosen by config alone (spec 01 D8) -------------


@pytest.mark.parametrize(
    ("chat_model", "expected_class"),
    [
        ("groq:openai/gpt-oss-120b", ChatGroq),
        ("openai:gpt-4.1-mini", ChatOpenAI),
        ("mistralai:ministral-8b-latest", ChatMistralAI),
    ],
)
def test_chat_model_provider_is_swapped_by_config_only(
    tmp_path, monkeypatch: pytest.MonkeyPatch, chat_model: str, expected_class: type
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    (tmp_path / "leave-policy.md").write_text("25 days of leave.")
    settings = Settings(chat_model=chat_model, corpus_dir=tmp_path)

    built = build_answerer(settings, embeddings=KeywordEmbeddings(VOCAB))

    assert isinstance(built.chat_model, expected_class)
    assert built.chat_model.temperature == pytest.approx(0, abs=1e-6)  # Groq sends 0 as 1e-8
