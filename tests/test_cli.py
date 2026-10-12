import pytest

from app import cli
from app.answering.answer import NO_ANSWER, Answerer
from app.config import Settings
from app.domain import Chunk
from app.retrieval.search import ChunkIndex
from tests.fakes import KeywordEmbeddings, ScriptedChatModel

CHUNKS = [
    Chunk(id="leave-policy:1:0", doc_id="leave-policy", source="annual-leave-policy.md", page=1,
          text="Full-time employees get 25 days of annual leave."),
]  # fmt: skip


def fake_build(*responses: str):
    def build(settings: Settings) -> Answerer:
        index = ChunkIndex(CHUNKS, KeywordEmbeddings(["leave"]))
        return Answerer(index, ScriptedChatModel(responses=list(responses)), top_k=5)

    return build


def test_answer_is_printed_with_its_sources(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["How much leave?"], build=fake_build("25 days [leave-policy:1]."))

    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("25 days [leave-policy:1].")
    assert "Sources:\n  - leave-policy:1 (annual-leave-policy.md)" in out
    assert "Retrieved" not in out


def test_no_answer_is_printed_without_sources_and_exits_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(["What about parental leave?"], build=fake_build(NO_ANSWER))

    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == NO_ANSWER


def test_debug_also_prints_retrieved_chunks_with_scores(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.main(["How much leave?", "--debug"], build=fake_build("25 days [leave-policy:1]."))

    out = capsys.readouterr().out
    assert "Retrieved (top 1):" in out  # the test corpus has one chunk
    assert "leave-policy:1:0" in out
    assert "status: answered" in out and "prompt: answer_v1" in out


def test_errors_exit_1_with_a_message(capsys: pytest.CaptureFixture[str]) -> None:
    def broken(settings: Settings) -> Answerer:
        raise RuntimeError("model unavailable")

    code = cli.main(["How much leave?"], build=broken)

    assert code == 1
    assert "Error: RuntimeError: model unavailable" in capsys.readouterr().err
