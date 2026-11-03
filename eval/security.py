"""Security evaluation (spec 07 D1–D3, ISS-059). Offline: local models only, no API keys.

    uv run python -m eval.security            # report → eval/reports/security-<time>.json

Input guard (rules + classifier) over the own adversarial and benign sets and the public slice;
context guard over the indirect passages and over every chunk of the real corpus (a dropped real
chunk is a false drop). Deterministic: the same code and models give the same verdicts, so two
runs can be compared case by case. Rates come with 95% Wilson intervals.
"""

import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from app.config import ROOT, Settings, get_settings
from app.domain import Chunk, ScoredChunk
from app.guards.context import ContextGuard
from app.guards.injection import InjectionClassifier, InputGuard, injection_classifier
from app.ingestion.chunking import chunk_pages
from app.ingestion.loaders import load_pages
from eval.metrics import wilson_interval

DATASETS = ROOT / "eval" / "datasets"
REPORTS = ROOT / "eval" / "reports"
CORPUS = ROOT / "data"  # every folder that holds documents: sample/ and each tenants/<name>/
DEV_SHARE = 3  # in 10: about 30% dev, 70% test


def split_of(case_id: str) -> str:
    """'dev' or 'test', fixed by the id's hash: stable across runs and machines, no extra field."""
    return (
        "dev" if int(hashlib.sha256(case_id.encode()).hexdigest(), 16) % 10 < DEV_SHARE else "test"
    )


def load_jsonl(name: str) -> list[dict]:
    lines = (DATASETS / name).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def rate(hits: int, n: int) -> dict:
    """A rate with its 95% interval, as the report stores it."""
    if n == 0:
        return {"hits": 0, "n": 0, "rate": None, "low": None, "high": None}
    low, high = wilson_interval(hits, n)
    return {
        "hits": hits,
        "n": n,
        "rate": round(hits / n, 4),
        "low": round(low, 4),
        "high": round(high, 4),
    }


# --- running the guards -----------------------------------------------------------------------


def input_rows(guard: InputGuard, cases: Iterable[dict], *, kind: str, source: str) -> list[dict]:
    """One row per case: was it blocked, by what, with what score."""
    rows = []
    for case in cases:
        verdict = guard.check(case["text"])
        rows.append(
            {
                "id": case["id"],
                "set": "input",
                "kind": kind,
                "source": source,
                "category": case.get("category", ""),
                "split": split_of(case["id"]),
                "blocked": verdict.decision == "BLOCK",
                "reason": verdict.reason,
                "score": verdict.score,
            }
        )
    return rows


def context_rows(
    guard: ContextGuard, passages: Iterable[tuple[str, str, str, str]], *, source: str
) -> list[dict]:
    """Each passage (id, kind, category, text) as one retrieved chunk: was it dropped?"""
    rows = []
    for case_id, kind, category, text in passages:
        chunk = Chunk(id=case_id, doc_id=case_id, source=source, page=1, text=text)
        _, verdicts = guard.check([ScoredChunk(chunk=chunk, score=1.0)], scope=None)
        drop = next((v for v in verdicts if v.decision == "DROP"), None)
        score = drop.score if drop else None
        if drop is None and guard.classifier is not None:  # kept: record how close it came
            score = round(guard.classifier.score(text), 4)
        rows.append(
            {
                "id": case_id,
                "set": "context",
                "kind": kind,
                "source": source,
                "category": category,
                "split": split_of(case_id),
                "blocked": drop is not None,
                "reason": drop.reason if drop else "",
                "score": score,
            }
        )
    return rows


def corpus_chunks(settings: Settings) -> list[Chunk]:
    """Every chunk of the real documents, chunked exactly as ingest does."""
    folders = sorted(
        {
            path.parent
            for path in CORPUS.rglob("*")
            if path.is_file() and not path.name.startswith(".")
        }
    )  # load_pages reads one folder
    pages = [page for folder in folders for page in load_pages(folder)]
    return chunk_pages(
        pages,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        encoding_name=settings.tokenizer_encoding,
    )


# --- summarising ------------------------------------------------------------------------------


def _blocked(rows: list[dict]) -> dict:
    return rate(sum(r["blocked"] for r in rows), len(rows))


def summarise(rows: list[dict]) -> dict:
    """The headline numbers. Own cases are scored on the test split (the gate's numbers) and on
    all cases; the public slice and the dev split are shown for comparison."""

    def pick(set_: str, kind: str, source: str = "own", split: str | None = None) -> list[dict]:
        return [
            r
            for r in rows
            if r["set"] == set_
            and r["kind"] == kind
            and r["source"] == source
            and (split is None or r["split"] == split)
        ]

    by_category = defaultdict(list)
    for r in pick("input", "attack", split="test"):
        by_category[r["category"]].append(r)
    hard_benign = [r for r in pick("input", "benign", split="test") if r["category"] == "hard"]
    return {
        "input_block_rate": _blocked(pick("input", "attack", split="test")),
        "input_false_refusal_rate": _blocked(pick("input", "benign", split="test")),
        "input_false_refusal_rate_hard": _blocked(hard_benign),
        "input_block_rate_all": _blocked(pick("input", "attack")),
        "input_false_refusal_rate_all": _blocked(pick("input", "benign")),
        "input_block_rate_dev": _blocked(pick("input", "attack", split="dev")),
        "input_block_by_category": {c: _blocked(rs) for c, rs in sorted(by_category.items())},
        "public_block_rate": _blocked(pick("input", "attack", source="public")),
        "public_false_refusal_rate": _blocked(pick("input", "benign", source="public")),
        "context_drop_rate": _blocked(pick("context", "attack", split="test")),
        "context_false_drop_rate": _blocked(pick("context", "benign", split="test")),
        "corpus_false_drops": _blocked(pick("context", "benign", source="corpus")),
    }


def build_report(rows: list[dict], settings: Settings, commit: str | None) -> dict:
    return {
        "kind": "security",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": commit,
        "config": {
            "injection_model": settings.injection_model,
            "injection_revision": settings.injection_revision,
            "injection_threshold": settings.injection_threshold,
        },
        "summary": summarise(rows),
        "rows": rows,
    }


def evaluate(
    settings: Settings,
    classifier: InjectionClassifier,
    *,
    progress: Callable[[str], None] = lambda _: None,
) -> list[dict]:
    """Run both guards over every set (the slow part: about a thousand classifier calls)."""
    input_guard = InputGuard(classifier, settings.injection_threshold)
    context_guard = ContextGuard(classifier, settings.injection_threshold)
    progress("input guard: own sets")
    rows = input_rows(input_guard, load_jsonl("adversarial.jsonl"), kind="attack", source="own")
    rows += input_rows(input_guard, load_jsonl("benign.jsonl"), kind="benign", source="own")
    progress("input guard: public slice")
    public = load_jsonl("public_deepset.jsonl")
    for label in ("attack", "benign"):
        cases = [c for c in public if c["label"] == label]
        rows += input_rows(input_guard, cases, kind=label, source="public")
    progress("context guard: indirect passages")
    passages = [
        (p["id"], p["kind"], p.get("category", ""), p["text"]) for p in load_jsonl("indirect.jsonl")
    ]
    rows += context_rows(context_guard, passages, source="own")
    progress("context guard: real corpus chunks")
    real = [(c.id, "benign", "corpus", c.text) for c in corpus_chunks(settings)]
    rows += context_rows(context_guard, real, source="corpus")
    return rows


def write_report(report: dict, prefix: str = "security") -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = report["created_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    path = REPORTS / f"{prefix}-{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path.relative_to(ROOT))


def print_summary(summary: dict) -> None:
    def line(name: str, r: dict) -> str:
        if not r["n"]:
            return f"  {name:34} -"
        return (
            f"  {name:34} {r['hits']:>3}/{r['n']:<3} = {r['rate']:.1%}"
            f"  (95% CI {r['low']:.1%}–{r['high']:.1%})"
        )

    for name, value in summary.items():
        if name == "input_block_by_category":
            print("  blocked by category (test split):")
            for category, r in value.items():
                print("  " + line(category, r))
        else:
            print(line(name, value))


def main() -> int:
    from eval.run import _git_commit

    settings = get_settings()
    rows = evaluate(settings, injection_classifier(settings), progress=lambda s: print(f"… {s}"))
    report = build_report(rows, settings, _git_commit())
    print_summary(report["summary"])
    print(f"\nreport: {write_report(report)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
