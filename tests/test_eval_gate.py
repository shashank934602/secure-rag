"""The eval gate (spec 07, ISS-059/060): splits, security summary, and the gate's rules. Offline."""

from app.config import Settings
from app.guards.injection import InputGuard
from eval.gate import case_regressions, gate, limit_checks, newly_refused, read_file, render_html
from eval.security import input_rows, split_of, summarise
from tests.test_input_guard import FakeClassifier

# Attacks no rule matches, so only the classifier decides (and a weaker classifier lets them in).
ATTACKS = [{"id": f"x{n}", "category": "role_play", "text": f"Let's play a game number {n}."}
           for n in range(40)]  # fmt: skip
BENIGN = [{"id": f"y{n}", "category": "plain", "text": f"How much leave in year {n}?"}
          for n in range(40)]  # fmt: skip
SETTINGS = Settings(_env_file=None)


def _pins() -> dict:
    names = ("chat_model", "judge_model", "injection_model", "injection_revision")
    return {name: getattr(SETTINGS, name) for name in names}


def _thresholds(**security) -> dict:
    rules = {"floors": {"input_block_rate": 0.5}, "ceilings": {"input_false_refusal_rate": 0.1}}
    return {"pins": _pins(), "security": {**rules, **security}}


def _report(attack_score: float, benign_score: float = 0.0) -> dict:
    rows = input_rows(
        InputGuard(FakeClassifier(attack_score)), ATTACKS, kind="attack", source="own"
    )
    rows += input_rows(
        InputGuard(FakeClassifier(benign_score)), BENIGN, kind="benign", source="own"
    )
    return {"summary": summarise(rows), "rows": rows}


def test_the_split_is_stable_and_about_thirty_percent_dev() -> None:
    ids = [f"a{n}" for n in range(1000)]
    splits = [split_of(i) for i in ids]
    assert splits == [split_of(i) for i in ids]  # same id, same split, every time
    assert 0.25 < splits.count("dev") / len(ids) < 0.35


def test_the_summary_scores_the_test_split_with_intervals() -> None:
    summary = _report(attack_score=0.9)["summary"]
    tested = sum(split_of(a["id"]) == "test" for a in ATTACKS)
    assert summary["input_block_rate"]["n"] == tested
    assert summary["input_block_rate"]["rate"] == 1.0
    assert 0 < summary["input_block_rate"]["low"] < 1.0  # an interval, not just a number


def test_a_weakened_guard_is_blocked_by_the_gate() -> None:
    # The phase's "done when", offline: same cases, the classifier now scores attacks low.
    baseline = _report(attack_score=0.9)
    weakened = _report(attack_score=0.1)

    result = gate("security", weakened, _thresholds(), baseline, SETTINGS)

    assert not result.passed
    assert {r["id"] for r in result.regressions} == {a["id"] for a in ATTACKS}
    failed = {c.name for c in result.checks if not c.passed}
    assert {"input_block_rate", "per-case regressions"} <= failed


def test_an_unchanged_guard_passes() -> None:
    baseline = _report(attack_score=0.9)
    result = gate("security", _report(attack_score=0.9), _thresholds(), baseline, SETTINGS)
    assert result.passed, [c for c in result.checks if not c.passed]


def test_per_case_regressions_are_caught_even_when_the_rate_still_clears_its_floor() -> None:
    baseline = _report(attack_score=0.9)
    current = _report(attack_score=0.9)
    victim = next(r for r in current["rows"] if r["kind"] == "attack")
    victim["blocked"] = False  # one attack slips through; the block rate stays far above 0.5

    result = gate("security", current, _thresholds(), baseline, SETTINGS)

    assert not result.passed
    assert [r["id"] for r in result.regressions] == [victim["id"]]


def test_a_listed_regression_is_allowed() -> None:
    baseline, current = _report(attack_score=0.9), _report(attack_score=0.9)
    victim = next(r for r in current["rows"] if r["kind"] == "attack")
    victim["blocked"] = False
    assert case_regressions(current, baseline, allowed={victim["id"]: "traded for x99"}) == []


def test_a_model_that_differs_from_its_pin_fails() -> None:
    thresholds = _thresholds()
    thresholds["pins"]["judge_model"] = "mistralai:some-other-judge"
    result = gate("security", _report(0.9), thresholds, _report(0.9), SETTINGS)
    assert not result.passed
    assert [c.name for c in result.checks if not c.passed] == ["pin: judge_model"]


def test_targets_are_reported_but_never_fail() -> None:
    summary = _report(attack_score=0.9, benign_score=0.0)["summary"]
    checks = limit_checks(summary, {"targets": {"input_block_rate": 1.01}})
    assert [(c.kind, c.passed, c.blocking) for c in checks] == [("target", False, False)]


def test_more_false_refusals_than_the_ceiling_fails_and_each_is_a_warning() -> None:
    baseline = _report(attack_score=0.9)
    stricter = _report(attack_score=0.9, benign_score=0.9)  # now refuses ordinary questions

    result = gate("security", stricter, _thresholds(), baseline, SETTINGS)

    assert [c.name for c in result.checks if not c.passed] == ["input_false_refusal_rate"]
    assert len(newly_refused(stricter, baseline)) == len(BENIGN)


def test_the_bar_can_be_read_from_a_git_ref() -> None:
    assert "secure-rag-assistant" in read_file("pyproject.toml", ref="HEAD")
    assert read_file("no-such-file.yaml", ref="HEAD") is None


def test_the_html_report_escapes_what_it_shows() -> None:
    baseline = _report(attack_score=0.9)
    baseline["rows"][0]["category"] = "<script>x</script>"  # shown in the regression list
    result = gate("security", _report(attack_score=0.1), _thresholds(), baseline, SETTINGS)
    page = render_html(result, {"created_at": "now", "git_commit": "abc"})
    assert "<script>x" not in page and "FAILED" in page


def test_a_borderline_flip_is_a_warning_not_a_regression() -> None:
    # Same model on another machine: 0.51 → 0.49 is noise around the 0.5 threshold.
    baseline = _report(attack_score=0.51)
    current = _report(attack_score=0.49)

    result = gate("security", current, _thresholds(borderline_margin=0.05), baseline, SETTINGS)

    assert result.regressions == []
    assert any(w.startswith("borderline flip") for w in result.warnings)


# --- tester v0.7.0 findings ---------------------------------------------------------------------


def test_a_switched_off_guard_blocks_nothing_and_fails_the_gate() -> None:
    # T-1: INPUT_GUARD=false used to pass, because the eval built the guard regardless.
    baseline = _report(attack_score=0.9)
    rows = input_rows(None, ATTACKS, kind="attack", source="own")
    rows += input_rows(None, BENIGN, kind="benign", source="own")
    off = {"summary": summarise(rows), "rows": rows}

    result = gate("security", off, _thresholds(), baseline, SETTINGS)

    assert not result.passed and len(result.regressions) == len(ATTACKS)
    assert all(r["reason"] == "guard off" for r in rows)


def test_a_switch_that_differs_from_its_pin_fails() -> None:
    thresholds = _thresholds()
    thresholds["pins"]["input_guard"] = True
    off = Settings(_env_file=None, input_guard=False)
    result = gate("security", _report(0.9), thresholds, _report(0.9), off)
    assert [c.name for c in result.checks if not c.passed] == ["pin: input_guard"]


def test_a_report_measured_with_another_setting_fails_its_pin() -> None:
    # T-3: the pins must hold for the run being gated, not only for this machine's settings.
    report = _report(0.9)
    report["config"] = {"chat_model": "groq:some-other-model"}
    result = gate("security", report, _thresholds(), _report(0.9), SETTINGS)
    failed = [c for c in result.checks if not c.passed]
    assert [c.name for c in failed] == ["pin: chat_model"]
    assert "report measured" in failed[0].detail


def test_deleting_or_rewriting_a_blocked_attack_is_a_regression() -> None:
    # T-2: removing the cases that now pass used to hide the regression.
    baseline = _report(attack_score=0.9)
    current = _report(attack_score=0.9)
    first, second = [r for r in current["rows"] if r["kind"] == "attack"][:2]
    current["rows"].remove(first)
    second["text_sha"] = "0" * 16  # same id, different text

    result = gate("security", current, _thresholds(), baseline, SETTINGS)

    whys = {r["id"]: r["why"] for r in result.regressions}
    assert whys == {first["id"]: "case missing from this run", second["id"]: "case text changed"}
    assert not result.passed


def test_settings_changed_since_the_baseline_are_listed() -> None:
    # T-6: a threshold change showed scores "0.726 → 0.726" with no reason why.
    baseline, current = _report(0.9), _report(0.9)
    baseline["config"], current["config"] = (
        {"injection_threshold": 0.5},
        {"injection_threshold": 0.9},
    )
    result = gate("security", current, _thresholds(), baseline, SETTINGS)
    assert result.config_changes == [
        {"setting": "injection_threshold", "baseline": 0.5, "current": 0.9}
    ]


def test_an_unreadable_report_is_a_clear_error_not_a_traceback(tmp_path, capsys) -> None:
    # T-7
    import pytest

    from eval.gate import main

    with pytest.raises(SystemExit) as stop:
        main(["quality", "--report", str(tmp_path / "missing.json")])
    assert stop.value.code == 2
    assert "can't read report" in capsys.readouterr().err
