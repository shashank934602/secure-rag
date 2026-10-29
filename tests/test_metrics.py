"""S6 (ISS-025): eval metrics — pure functions, checked by hand-worked examples."""

import pytest

from eval.metrics import (
    QuestionResult,
    key_fact_score,
    no_answer_correct,
    normalise,
    percentile,
    recall_at_k,
    reciprocal_rank,
    summarise,
)

# --- recall@k: share of the expected pages found in the top k -----------------------------------


def test_recall_is_1_when_every_expected_page_is_in_the_top_k() -> None:
    assert recall_at_k(["leave:1"], ["leave:1", "expense:1"], k=5) == 1.0


def test_recall_counts_each_expected_page_once() -> None:
    # Two expected pages, one found: half. Several chunks of one page don't count twice.
    assert recall_at_k(["leave:1", "org:1"], ["leave:1", "leave:1", "expense:1"], k=5) == 0.5


def test_recall_ignores_pages_below_the_top_k() -> None:
    retrieved = ["a:1", "b:1", "c:1", "d:1", "e:1", "leave:1"]  # the right page is 6th
    assert recall_at_k(["leave:1"], retrieved, k=5) == 0.0


def test_recall_needs_expected_pages() -> None:
    with pytest.raises(ValueError):
        recall_at_k([], ["leave:1"], k=5)  # unanswerable questions have no recall


# --- reciprocal rank: 1 / position of the first right page --------------------------------------


@pytest.mark.parametrize(
    ("retrieved", "expected_rr"),
    [
        (["leave:1", "a:1"], 1.0),
        (["a:1", "leave:1"], 0.5),
        (["a:1", "b:1", "c:1", "leave:1"], 0.25),
        (["a:1", "b:1"], 0.0),
    ],
)
def test_reciprocal_rank(retrieved, expected_rr) -> None:
    assert reciprocal_rank(["leave:1"], retrieved) == expected_rr


def test_reciprocal_rank_uses_the_first_of_several_expected_pages() -> None:
    assert reciprocal_rank(["org:1", "contract:3"], ["a:1", "contract:3", "org:1"]) == 0.5


# --- key facts: normalising real model output ---------------------------------------------------


def test_normalise_handles_real_model_formatting() -> None:
    # Real replies from gpt-oss-120b (2026-10-29): bold, narrow no-break spaces, odd hyphens.
    assert normalise("**5 mph**") == "5 mph"
    assert normalise("555‑0150") == "555-0150"
    assert normalise("Full‑time   employees\n**25 days**") == "full-time employees 25 days"


def test_key_fact_score_is_the_share_of_facts_found() -> None:
    answer = "Report it within 24 hours using the **SafeSite** app."
    assert key_fact_score(answer, ["24 hours", "SafeSite"]) == 1.0
    assert key_fact_score(answer, ["24 hours", "paper form", "site office"]) == pytest.approx(1 / 3)


def test_key_facts_are_matched_on_real_answers() -> None:
    real = (
        "You must report a lost work laptop **within 1 hour** of noticing it. Report it to the IT "
        "Service Desk by calling **555‑0150** or by emailing **security@aldermoor.example.com**"
        "【it-security-policy:1】."
    )
    assert key_fact_score(real, ["1 hour", "555-0150", "security@aldermoor.example.com"]) == 1.0


def test_a_no_answer_scores_zero_on_key_facts() -> None:
    assert key_fact_score("I don't know based on the documents I can access.", ["25 days"]) == 0.0


def test_key_fact_score_needs_key_facts() -> None:
    with pytest.raises(ValueError):
        key_fact_score("anything", [])


# --- No-Answer: "I don't know" exactly when it should --------------------------------------------


@pytest.mark.parametrize(
    ("status", "answerable", "correct"),
    [
        ("no_answer", False, True),  # trick question refused: right
        ("answered", False, False),  # trick question answered: invented
        ("answered", True, True),
        ("no_answer", True, False),  # real question refused: a false refusal
    ],
)
def test_no_answer_correct(status, answerable, correct) -> None:
    assert no_answer_correct(status, answerable) is correct


# --- latency percentiles --------------------------------------------------------------------------


def test_percentile_interpolates_between_values() -> None:
    times = [1.0, 2.0, 3.0, 4.0, 10.0]
    assert percentile(times, 50) == 3.0
    assert percentile(times, 100) == 10.0
    assert percentile(times, 0) == 1.0
    assert percentile(times, 95) == pytest.approx(8.8)  # 4 + 0.8 * (10 - 4)


def test_percentile_of_one_value_is_that_value() -> None:
    assert percentile([2.5], 95) == 2.5


def test_percentile_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1.0], 101)


# --- the summary over a run ----------------------------------------------------------------------


def _result(qid, answerable, sources, facts, retrieved, status, answer, latency) -> QuestionResult:
    return QuestionResult(
        id=qid,
        answerable=answerable,
        expected_sources=sources,
        key_facts=facts,
        retrieved=retrieved,
        status=status,
        answer=answer,
        latency_s=latency,
    )


def test_summary_of_a_small_run() -> None:
    results = [
        # answered, right page first, both facts → recall 1, rr 1, facts 1
        _result("q1", True, ["leave:1"], ["25 days", "8 bank holidays"],
                ["leave:1", "x:1"], "answered", "25 days plus 8 bank holidays", 1.0),
        # right page second, one of two facts → recall 1, rr 0.5, facts 0.5
        _result("q2", True, ["expense:1"], ["£190", "room only"],
                ["x:1", "expense:1"], "answered", "£190 per night", 2.0),
        # retrieval miss, refused → recall 0, rr 0, facts 0, a false refusal
        _result("q3", True, ["org:1"], ["Hannah Brooks"],
                ["x:1", "y:1"], "no_answer", "I don't know", 3.0),
        # trick question refused → correct
        _result("q4", False, [], [], ["x:1"], "no_answer", "I don't know", 4.0),
    ]  # fmt: skip

    s = summarise(results)

    assert s["questions"] == 4
    assert s["recall_at_5"] == pytest.approx(2 / 3)
    assert s["mrr"] == pytest.approx(0.5)  # (1 + 0.5 + 0) / 3
    assert s["key_fact_score"] == pytest.approx(0.5)  # (1 + 0.5 + 0) / 3
    assert s["answered_rate"] == pytest.approx(2 / 3)
    assert s["false_refusals"] == 1
    assert s["no_answer_accuracy"] == 1.0
    assert s["latency_p50_s"] == pytest.approx(2.5)
    assert s["latency_p95_s"] == pytest.approx(3.85)
