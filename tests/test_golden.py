"""S5 (ISS-024): the golden set is valid — every key fact really is on its expected page."""

import json
from pathlib import Path

from app.config import ROOT
from scripts.check_golden import check

DATASET = ROOT / "eval" / "datasets" / "golden.jsonl"
CORPUS = ROOT / "data" / "sample"
NO_ANSWER = "I don't know based on the documents I can access."


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "golden.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return path


def _rows() -> list[dict]:
    return [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]


def test_the_real_golden_set_passes() -> None:
    assert check(DATASET, CORPUS) == []


def test_it_has_20_questions_14_answerable_and_6_not() -> None:
    rows = _rows()
    assert len(rows) == 20
    assert sum(r["answerable"] for r in rows) == 14


def test_a_wrong_key_fact_is_caught(tmp_path) -> None:
    rows = _rows()
    rows[0]["key_facts"] = ["26 days"]  # the leave policy says 25
    errors = check(_write(tmp_path, rows), CORPUS)
    assert any("g01" in e and "26 days" in e for e in errors)


def test_a_missing_source_page_is_caught(tmp_path) -> None:
    rows = _rows()
    rows[0]["expected_sources"] = ["annual-leave-policy:2"]  # Markdown has only page 1
    errors = check(_write(tmp_path, rows), CORPUS)
    assert any("g01" in e and "annual-leave-policy:2" in e for e in errors)


def test_a_duplicate_id_is_caught(tmp_path) -> None:
    rows = _rows()
    rows[1]["id"] = rows[0]["id"]
    assert any("duplicate" in e for e in check(_write(tmp_path, rows), CORPUS))


def test_an_unanswerable_question_must_expect_the_no_answer(tmp_path) -> None:
    rows = _rows()
    unanswerable = next(r for r in rows if not r["answerable"])
    unanswerable["expected_answer"] = "Something made up."
    unanswerable["key_facts"] = ["made up"]
    errors = check(_write(tmp_path, rows), CORPUS)
    assert any(unanswerable["id"] in e for e in errors)


def test_an_answerable_question_needs_sources_and_key_facts(tmp_path) -> None:
    rows = _rows()
    rows[0]["key_facts"] = []
    assert any("g01" in e for e in check(_write(tmp_path, rows), CORPUS))


def test_unanswerable_questions_expect_the_exact_no_answer_sentence() -> None:
    for row in _rows():
        if not row["answerable"]:
            assert row["expected_answer"] == NO_ANSWER
            assert row["expected_sources"] == [] and row["key_facts"] == []
