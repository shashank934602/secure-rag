"""Smoke test against the real models and the sample corpus.

Skipped by default. Run with `uv run pytest -m live`; needs API keys in .env, costs under a cent.
Quality is measured by the eval harness, not here — this only checks the pieces connect.
"""

import json
from pathlib import Path

import pytest

from app.answering.answer import build_answerer
from app.config import get_settings

pytestmark = pytest.mark.live

GOLDEN = Path(__file__).resolve().parent.parent / "eval" / "datasets" / "golden.jsonl"
CASES = {row["id"]: row for row in map(json.loads, GOLDEN.read_text().splitlines())}


@pytest.fixture(scope="module")
def answerer():
    return build_answerer(get_settings())


def test_answerable_question_gets_a_cited_answer(answerer) -> None:
    case = CASES["g01"]

    result = answerer.answer(case["question"])

    assert result.status == "answered"
    assert {str(c) for c in result.citations} & set(case["expected_sources"])


def test_unanswerable_question_gets_no_answer(answerer) -> None:
    result = answerer.answer(CASES["g10"]["question"])

    assert result.status == "no_answer"
