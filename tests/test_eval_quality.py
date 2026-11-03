"""Phase 7 quality metrics (spec 07 D4, D9, ISS-061): tokens, cost, the eval judge. Offline."""

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.answering.answer import NO_ANSWER, Answerer
from app.config import Settings
from app.domain import Chunk
from app.retrieval.search import ChunkIndex
from eval.judges import EvalJudge, parse_claims
from eval.metrics import QuestionResult, cost_per_query, judged_scores
from eval.run import build_report, evaluate
from tests.fakes import KeywordEmbeddings, ScriptedChatModel

CHUNKS = [
    Chunk(id="leave:1:0", doc_id="leave", source="leave.md", page=1, text="Leave is 25 days.")
]
ROWS = [
    {
        "id": "q1",
        "question": "How much leave?",
        "answerable": True,
        "expected_sources": ["leave:1"],
        "key_facts": ["25 days"],
        "expected_answer": "25 days of annual leave.",
    },
    {
        "id": "q2",
        "question": "What is the CEO's salary?",
        "answerable": False,
        "expected_sources": [],
        "key_facts": [],
        "expected_answer": "",
    },
]


class MeteredModel(ScriptedChatModel):
    """A scripted model that reports token usage, as real providers do."""

    def _generate(self, messages, stop=None, **kwargs) -> ChatResult:
        self.calls.append(messages)
        text = self.responses[len(self.calls) - 1]
        message = AIMessage(
            content=text,
            usage_metadata={"input_tokens": 1000, "output_tokens": 50, "total_tokens": 1050},
            response_metadata={"model_name": "openai/gpt-oss-120b"},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])


def _answerer(model) -> Answerer:
    return Answerer(
        index=ChunkIndex(CHUNKS, KeywordEmbeddings(["leave"])), chat_model=model, top_k=1
    )


def _result(**fields) -> QuestionResult:
    base = {
        "id": "q",
        "answerable": True,
        "expected_sources": ["leave:1"],
        "key_facts": ["25"],
        "retrieved": ["leave:1"],
        "status": "answered",
        "answer": "25",
        "latency_s": 1.0,
    }
    return QuestionResult(**{**base, **fields})


def test_every_answer_reports_its_tokens_per_model() -> None:
    result = _answerer(MeteredModel(responses=["Leave is 25 days [leave:1]."])).answer("leave?")
    assert result.usage == {
        "openai/gpt-oss-120b": {"input_tokens": 1000, "output_tokens": 50, "total_tokens": 1050}
    }


def test_cost_per_query_uses_list_prices_and_names_unpriced_models() -> None:
    usage = {
        "openai/gpt-oss-120b": {"input_tokens": 1000, "output_tokens": 50, "total_tokens": 1050},
        "mystery-model": {"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
    }
    prices = {"groq:openai/gpt-oss-120b": {"input": 0.15, "output": 0.60}}

    out = cost_per_query([_result(usage=usage), _result()], prices)

    # (1000 × 0.15 + 50 × 0.60) / 1e6 = 0.00018 for the first question; averaged over two.
    assert out["cost_per_query_usd"] == 0.00009
    assert out["tokens_per_query"] == 535.0
    assert out["unpriced_models"] == ["mystery-model"]


def test_judged_scores_count_a_missing_answer_as_wrong_and_skip_what_wasnt_scored() -> None:
    results = [
        _result(correctness=1.0, faithfulness=1.0),
        _result(status="no_answer", answer=NO_ANSWER),  # answerable but not answered → 0
        _result(correctness=None, faithfulness=0.5),  # the judge couldn't score correctness
    ]
    scores = judged_scores(results)
    assert scores == {"correctness": 0.5, "faithfulness": 0.75, "judge_unscored": 1}


def test_the_judge_reply_must_be_well_formed() -> None:
    assert parse_claims('{"claims": [{"claim": "25 days", "present": true}]}', "present") == (
        [True],
        {"claims": [{"claim": "25 days", "present": True}]},
    )
    assert parse_claims('{"claims": [{"claim": "x", "present": "yes"}]}', "present") is None
    assert parse_claims("I think it's fine", "present") is None


def test_a_contradiction_scores_zero_and_an_unreadable_judge_scores_none() -> None:
    contradicts = '{"claims": [{"claim": "25 days", "present": true}], "contradicts": true}'
    assert EvalJudge(ScriptedChatModel(responses=[contradicts])).correctness("q", "25", "40") == 0.0
    unreadable = EvalJudge(ScriptedChatModel(responses=["no idea", "still no idea"]))
    assert unreadable.faithfulness("25 days", ["Leave is 25 days."]) is None


def test_the_eval_run_scores_answers_with_the_judge_and_reports_cost() -> None:
    model = MeteredModel(responses=["Leave is 25 days [leave:1].", NO_ANSWER])
    judge = EvalJudge(
        ScriptedChatModel(
            responses=[
                '{"claims": [{"claim": "25 days", "present": true}], "contradicts": false}',
                '{"claims": [{"claim": "Leave is 25 days", "supported": true}]}',
            ]
        )
    )

    results = evaluate(ROWS, _answerer(model), k=1, judge=judge)
    report = build_report(results, Settings(_env_file=None))

    assert (results[0].correctness, results[0].faithfulness) == (1.0, 1.0)
    assert (results[1].correctness, results[1].faithfulness) == (None, None)  # not answered
    assert report["summary"]["correctness"] == 1.0
    assert report["summary"]["cost_per_query_usd"] > 0
    assert report["config"]["eval_judge_model"] == "mistralai:mistral-small-2603"


def test_a_rate_limited_judge_waits_and_retries_then_gives_up_without_crashing() -> None:
    class Flaky(ScriptedChatModel):
        failed: bool = False

        def _generate(self, *args, **kwargs):
            if not self.failed:  # the first call is rate limited
                self.failed = True
                raise RuntimeError("429 rate limited")
            return super()._generate(*args, **kwargs)

    waits = []
    reply = '{"claims": [{"claim": "Leave is 25 days", "supported": true}]}'
    flaky = Flaky(responses=[reply])
    assert (
        EvalJudge(flaky, sleep=waits.append).faithfulness("25 days", ["Leave is 25 days."]) == 1.0
    )
    assert waits == [10.0]

    class Down(ScriptedChatModel):
        def _generate(self, *args, **kwargs):
            raise RuntimeError("429 rate limited")

    waits.clear()
    assert EvalJudge(Down(responses=[]), sleep=waits.append).correctness("q", "25", "25") is None
    assert waits == [10.0, 20.0]
