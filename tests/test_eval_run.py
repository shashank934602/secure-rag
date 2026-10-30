"""S7 (ISS-026): the eval runner — golden questions through the API, scored, written as a report."""

import json
from pathlib import Path

from app.answering.answer import NO_ANSWER, Answerer
from app.config import Settings
from app.domain import Chunk
from app.retrieval.search import ChunkIndex
from eval.run import build_report, evaluate, write_report
from tests.fakes import KeywordEmbeddings, ScriptedChatModel

VOCAB = ["leave", "hotel"]
CHUNKS = [
    Chunk(id="leave:1:0", doc_id="leave", source="leave.md", page=1, text="Leave is 25 days."),
    Chunk(id="hotel:1:0", doc_id="hotel", source="hotel.md", page=1, text="Hotel limit £190."),
]
ROWS = [
    {"id": "q1", "question": "How much leave?", "answerable": True,
     "expected_sources": ["leave:1"], "key_facts": ["25 days"]},
    {"id": "q2", "question": "What is the CEO's salary?", "answerable": False,
     "expected_sources": [], "key_facts": []},
]  # fmt: skip


def _answerer(model) -> Answerer:
    return Answerer(index=ChunkIndex(CHUNKS, KeywordEmbeddings(VOCAB)), chat_model=model, top_k=2)


def _clock(*times: float):
    return iter(times).__next__


def test_each_question_is_answered_through_the_api_and_scored() -> None:
    model = ScriptedChatModel(responses=["Leave is 25 days [leave:1].", NO_ANSWER])

    results = evaluate(ROWS, _answerer(model), k=2, clock=_clock(0.0, 1.5, 2.0, 4.0))

    q1, q2 = results
    assert (q1.status, q1.retrieved[0], q1.latency_s) == ("answered", "leave:1", 1.5)
    assert q1.answer == "Leave is 25 days [leave:1]."
    assert (q2.status, q2.latency_s) == ("no_answer", 2.0)


def test_a_failed_request_is_retried() -> None:
    class FlakyModel(ScriptedChatModel):
        failures: int = 1

        def _generate(self, *args, **kwargs):
            if self.failures:
                self.failures -= 1
                raise RuntimeError("rate limited")
            return super()._generate(*args, **kwargs)

    model = FlakyModel(responses=["Leave is 25 days [leave:1]."])

    (result,) = evaluate(ROWS[:1], _answerer(model), k=2, retry_wait_s=0)

    assert result.status == "answered"


def test_a_request_that_keeps_failing_is_recorded_as_an_error() -> None:
    class BrokenModel(ScriptedChatModel):
        def _generate(self, *args, **kwargs):
            raise RuntimeError("down")

    (result,) = evaluate(ROWS[:1], _answerer(BrokenModel(responses=[])), k=2, retry_wait_s=0)

    assert (result.status, result.answer) == ("error", "")


def test_the_report_has_config_summary_and_every_question(tmp_path: Path) -> None:
    model = ScriptedChatModel(responses=["Leave is 25 days [leave:1].", NO_ANSWER])
    results = evaluate(ROWS, _answerer(model), k=2)

    report = build_report(results, Settings())
    path = write_report(report, tmp_path / "reports")

    saved = json.loads(path.read_text())
    assert saved["config"]["chat_model"] == Settings().chat_model
    assert saved["config"]["prompt_version"] == "answer_v1"
    assert saved["summary"]["questions"] == 2
    assert saved["summary"]["key_fact_score"] == 1.0
    assert saved["summary"]["no_answer_accuracy"] == 1.0
    assert saved["errors"] == 0
    assert [r["id"] for r in saved["results"]] == ["q1", "q2"]
