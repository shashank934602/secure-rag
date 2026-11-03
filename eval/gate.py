"""The eval gate (spec 07 D5–D7, ADR-0006, ISS-060): does a run meet the bar?

    uv run python -m eval.gate security                     # run eval.security, then gate it
    uv run python -m eval.gate security --report PATH       # gate an existing report
    uv run python -m eval.gate quality --report PATH        # gate an eval.run report
    uv run python -m eval.gate security --from-ref origin/main   # the bar comes from main (CI)
    uv run python -m eval.gate security --save-baseline     # after a reviewed improvement

Three kinds of check: **hard** (pinned models, per-case regressions, leaks, errors), **floors and
ceilings** (a ratchet just below the baseline), and **targets** (the architecture's goals:
reported, never failing). Writes JSON + HTML next to the eval reports, and a Markdown summary to
$GITHUB_STEP_SUMMARY in CI. Exit code 1 when any hard check, floor, or ceiling fails.

`--from-ref` reads the thresholds and the baseline from a git ref instead of the working tree, so
a pull request can't lower its own bar: a change to the bar takes effect only once merged.
"""

import argparse
import html
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.config import ROOT, Settings, get_settings

THRESHOLDS = "eval/thresholds.yaml"
REPORTS = ROOT / "eval" / "reports"


@dataclass(frozen=True)
class Check:
    name: str
    kind: str  # "hard", "floor", "ceiling", "target"
    value: float | int | str | None
    limit: float | int | str | None
    passed: bool
    detail: str = ""

    @property
    def blocking(self) -> bool:
        return self.kind != "target"


@dataclass
class GateResult:
    suite: str
    checks: list[Check] = field(default_factory=list)
    regressions: list[dict] = field(default_factory=list)  # per-case, blocking
    warnings: list[str] = field(default_factory=list)
    diff: list[dict] = field(default_factory=list)  # metric, baseline, current, delta
    bar_from: str = "working tree"

    @property
    def passed(self) -> bool:
        return not any(c.blocking and not c.passed for c in self.checks)


# --- reading the bar --------------------------------------------------------------------------


def read_file(path: str, ref: str | None = None) -> str | None:
    """A repo file from the working tree, or from a git ref (None if it doesn't exist there)."""
    if ref is None:
        target = ROOT / path
        return target.read_text(encoding="utf-8") if target.exists() else None
    out = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, cwd=ROOT)
    return out.stdout if out.returncode == 0 else None


def load_bar(suite: str, ref: str | None = None) -> tuple[dict, dict | None]:
    """(thresholds, baseline report or None) for a suite, from the working tree or a ref."""
    text = read_file(THRESHOLDS, ref)
    if text is None:
        raise SystemExit(f"no {THRESHOLDS} at {ref or 'working tree'}")
    thresholds = yaml.safe_load(text)
    baseline_text = read_file(thresholds[suite]["baseline"], ref)
    return thresholds, json.loads(baseline_text) if baseline_text else None


# --- checks -----------------------------------------------------------------------------------


def pin_checks(settings: Settings, pins: dict) -> list[Check]:
    """Every pinned model must be what the configuration actually uses (hard)."""
    checks = []
    for name, pinned in pins.items():
        actual = getattr(settings, name, None)
        checks.append(
            Check(
                f"pin: {name}",
                "hard",
                actual,
                pinned,
                actual == pinned,
                "" if actual == pinned else "re-baseline before changing a pin",
            )
        )
    return checks


def _value(summary: dict, metric: str) -> float | None:
    """A summary metric: a plain number, or the `rate` of a {hits, n, rate, …} entry."""
    value = summary.get(metric)
    return value.get("rate") if isinstance(value, dict) else value


def limit_checks(summary: dict, limits: dict) -> list[Check]:
    checks = []
    for kind, compare in (("floors", float.__ge__), ("ceilings", float.__le__)):
        for metric, limit in (limits.get(kind) or {}).items():
            value = _value(summary, metric)
            passed = value is not None and compare(float(value), float(limit))
            checks.append(Check(metric, kind.rstrip("s"), value, limit, passed))
    for metric, goal in (limits.get("targets") or {}).items():
        value = _value(summary, metric)
        better = float.__le__ if metric in (limits.get("lower_is_better") or []) else float.__ge__
        met = value is not None and better(float(value), float(goal))
        checks.append(Check(metric, "target", value, goal, met))
    return checks


def _threshold(report: dict) -> float:
    return float((report.get("config") or {}).get("injection_threshold", 0.5))


def case_regressions(
    report: dict, baseline: dict | None, allowed: dict, margin: float = 0.0
) -> list[dict]:
    """Own attacks (input and context) the baseline blocked and this run lets through.

    A flip is *borderline* when both scores sit within `margin` of the threshold each run used:
    the same model on another machine (CPU vs Apple GPU) can move a score by a hair, so those are
    warnings. A weakened guard moves scores or thresholds far more than that."""
    if not baseline:
        return []
    now = {(r["set"], r["id"]): r for r in report["rows"]}
    t_before, t_now = _threshold(baseline), _threshold(report)
    regressions = []
    for before in baseline["rows"]:
        if before["kind"] != "attack" or before["source"] != "own" or not before["blocked"]:
            continue
        after = now.get((before["set"], before["id"]))
        if after is not None and not after["blocked"] and before["id"] not in allowed:
            regressions.append(
                {
                    "set": before["set"],
                    "id": before["id"],
                    "category": before["category"],
                    "score_before": before["score"],
                    "score_now": after["score"],
                    "borderline": _near(before["score"], t_before, margin)
                    and _near(after["score"], t_now, margin),
                }
            )
    return regressions


def _near(score: float | None, threshold: float, margin: float) -> bool:
    return score is not None and abs(score - threshold) <= margin


def newly_refused(report: dict, baseline: dict | None) -> list[str]:
    """Benign cases this run refuses that the baseline let through (warnings, not failures)."""
    if not baseline:
        return []
    before = {
        (r["set"], r["id"]) for r in baseline["rows"] if r["kind"] == "benign" and r["blocked"]
    }
    return [
        f"{r['set']} {r['id']} now refused ({r['reason']})"
        for r in report["rows"]
        if r["kind"] == "benign" and r["blocked"] and (r["set"], r["id"]) not in before
    ]


def metric_diff(summary: dict, baseline: dict | None, metrics: list[str]) -> list[dict]:
    rows = []
    for metric in metrics:
        current = _value(summary, metric)
        before = _value(baseline["summary"], metric) if baseline else None
        delta = (
            round(current - before, 4)
            if isinstance(current, int | float) and isinstance(before, int | float)
            else None
        )
        rows.append({"metric": metric, "baseline": before, "current": current, "delta": delta})
    return rows


def gate(
    suite: str, report: dict, thresholds: dict, baseline: dict | None, settings: Settings
) -> GateResult:
    rules = thresholds[suite]
    result = GateResult(suite)
    result.checks += pin_checks(settings, thresholds["pins"])
    result.checks += limit_checks(report["summary"], rules)
    for metric, limit in (rules.get("hard") or {}).items():  # e.g. leaks: 0, errors: 0
        value = report.get(metric, report["summary"].get(metric))
        value = _value({"v": value}, "v")
        passed = value is not None and float(value) <= float(limit)
        result.checks.append(Check(metric, "hard", value, limit, passed))
    if suite == "security":
        allowed = rules.get("allowed_regressions") or {}
        margin = float(rules.get("borderline_margin", 0.0))
        flips = case_regressions(report, baseline, allowed, margin)
        result.regressions = [f for f in flips if not f["borderline"]]
        result.warnings += [
            f"borderline flip {f['set']} {f['id']}: {f['score_before']} → "
            f"{f['score_now']} (within {margin} of the threshold)"
            for f in flips
            if f["borderline"]
        ]
        result.checks.append(
            Check(
                "per-case regressions",
                "hard",
                len(result.regressions),
                0,
                not result.regressions,
                "attacks the baseline blocked that now pass",
            )
        )
        result.warnings += newly_refused(report, baseline)
    if baseline is None:
        result.warnings.append("no baseline: per-case and diff checks skipped")
    tracked = [
        *(rules.get("floors") or {}),
        *(rules.get("ceilings") or {}),
        *(rules.get("report") or []),
    ]
    result.diff = metric_diff(report["summary"], baseline, list(dict.fromkeys(tracked)))
    return result


# --- rendering --------------------------------------------------------------------------------


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return "–" if value is None else str(value)


def render_markdown(result: GateResult) -> str:
    verdict = "✅ PASSED" if result.passed else "❌ FAILED"
    lines = [
        f"## Eval gate — {result.suite}: {verdict}",
        "",
        f"Bar (thresholds + baseline) from: `{result.bar_from}`",
        "",
        "| Check | Kind | Value | Limit | Result |",
        "|---|---|---|---|---|",
    ]
    for c in result.checks:
        mark = "✅" if c.passed else ("⚠️ missed" if c.kind == "target" else "❌")
        lines.append(f"| {c.name} | {c.kind} | {_fmt(c.value)} | {_fmt(c.limit)} | {mark} |")
    if result.regressions:
        lines += ["", "### Per-case regressions (blocked before, pass now)", ""]
        lines += [
            f"- `{r['set']}` **{r['id']}** [{r['category']}] score "
            f"{_fmt(r['score_before'])} → {_fmt(r['score_now'])}"
            for r in result.regressions
        ]
    if result.diff:
        lines += [
            "",
            "### Diff against the baseline",
            "",
            "| Metric | Baseline | Now | Δ |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {d['metric']} | {_fmt(d['baseline'])} | {_fmt(d['current'])} | {_fmt(d['delta'])} |"
            for d in result.diff
        ]
    if result.warnings:
        lines += ["", "### Warnings", ""] + [f"- {w}" for w in result.warnings[:50]]
    return "\n".join(lines) + "\n"


_STYLE = """
:root { --bg:#fff; --fg:#1d1d1f; --muted:#666; --line:#ddd; --ok:#1a7f37; --bad:#c62828;
        --warn:#9a6700; }
@media (prefers-color-scheme: dark) { :root { --bg:#111; --fg:#eee; --muted:#aaa; --line:#333;
        --ok:#4ac26b; --bad:#ff6b6b; --warn:#e3b341; } }
body { background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif;
       max-width:960px; margin:2rem auto; padding:0 16px; }
table { border-collapse:collapse; width:100%; margin:1rem 0; }
th, td { border-bottom:1px solid var(--line); padding:6px 8px; text-align:left; }
.ok { color:var(--ok); } .bad { color:var(--bad); } .warn { color:var(--warn); }
.muted { color:var(--muted); }
"""


def render_html(result: GateResult, report: dict) -> str:
    def row(cells: list[str]) -> str:
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    verdict = (
        '<span class="ok">PASSED</span>' if result.passed else '<span class="bad">FAILED</span>'
    )
    checks = "".join(
        row(
            [
                html.escape(c.name),
                c.kind,
                _fmt(c.value),
                _fmt(c.limit),
                '<span class="ok">ok</span>'
                if c.passed
                else (
                    '<span class="warn">missed</span>'
                    if c.kind == "target"
                    else '<span class="bad">fail</span>'
                ),
            ]
        )
        for c in result.checks
    )
    diff = "".join(
        row([html.escape(d["metric"]), _fmt(d["baseline"]), _fmt(d["current"]), _fmt(d["delta"])])
        for d in result.diff
    )
    regressions = "".join(
        f"<li><b>{html.escape(r['id'])}</b> ({html.escape(r['set'])}, "
        f"{html.escape(r['category'])}): {_fmt(r['score_before'])} → "
        f"{_fmt(r['score_now'])}</li>"
        for r in result.regressions
    )
    warnings = "".join(f"<li>{html.escape(w)}</li>" for w in result.warnings[:200])
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval gate {html.escape(result.suite)}</title><style>{_STYLE}</style></head><body>
<h1>Eval gate — {html.escape(result.suite)}: {verdict}</h1>
<p class="muted">Run {html.escape(str(report.get("created_at")))} · commit
{html.escape(str(report.get("git_commit")))} · bar from {html.escape(result.bar_from)}</p>
<h2>Checks</h2><table><tr><th>Check</th><th>Kind</th><th>Value</th><th>Limit</th><th>Result</th>
</tr>{checks}</table>
<h2>Per-case regressions</h2>{f"<ul>{regressions}</ul>" if regressions else "<p>None.</p>"}
<h2>Diff against the baseline</h2><table><tr><th>Metric</th><th>Baseline</th><th>Now</th>
<th>Δ</th></tr>{diff}</table>
<h2>Warnings</h2>{f"<ul>{warnings}</ul>" if warnings else "<p>None.</p>"}
</body></html>
"""


def write_outputs(result: GateResult, report: dict) -> tuple[Path, Path]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = REPORTS / f"gate-{result.suite}-{stamp}"
    payload = {**asdict(result), "passed": result.passed}
    base.with_suffix(".json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    base.with_suffix(".html").write_text(render_html(result, report), encoding="utf-8")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as fh:
            fh.write(render_markdown(result))
    return base.with_suffix(".json"), base.with_suffix(".html")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.gate", description=__doc__.split("\n")[0])
    parser.add_argument("suite", choices=["security", "quality"])
    parser.add_argument("--report", help="an existing report (security runs eval.security if not)")
    parser.add_argument("--from-ref", help="read thresholds + baseline from this git ref")
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="write this report as the suite's baseline (after review)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    thresholds, baseline = load_bar(args.suite, args.from_ref)
    if args.report:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    elif args.suite == "security":
        from eval.run import _git_commit
        from eval.security import build_report, evaluate, injection_classifier, write_report

        rows = evaluate(
            settings, injection_classifier(settings), progress=lambda s: print(f"… {s}")
        )
        report = build_report(rows, settings, _git_commit())
        print(f"report: {write_report(report)}")
    else:
        parser.error("quality needs --report (from `python -m eval.run`)")

    result = gate(args.suite, report, thresholds, baseline, settings)
    result.bar_from = args.from_ref or "working tree"
    print(render_markdown(result))
    json_path, html_path = write_outputs(result, report)
    print(f"gate: {json_path.relative_to(ROOT)} · {html_path.relative_to(ROOT)}")
    if args.save_baseline:
        target = ROOT / thresholds[args.suite]["baseline"]
        target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"baseline: {target.relative_to(ROOT)}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
