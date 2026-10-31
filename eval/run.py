"""Run the golden set through the API and score it (spec 02 step 8, ISS-026).

    uv run python -m eval.run                          # report → eval/reports/<time>.json
    uv run python -m eval.run --save-baseline phase3   # also → eval/baselines/phase3.json

Retrieval settings come from the environment, e.g. RETRIEVAL_MODE=hybrid RERANK=true.

Answers go through the real API in-process (FastAPI test client), with the real models and the
database; retrieval metrics come from the same answerer's retriever, since the API doesn't return
chunks. Free-tier models sometimes refuse a burst of calls, so a failed request is retried.
"""

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.answering.answer import PROMPT_VERSION, Answerer, build_db_answerer
from app.config import ROOT, Settings, get_settings
from app.main import create_app
from eval.metrics import QuestionResult, key_fact_score, recall_at_k, reciprocal_rank, summarise

GOLDEN = ROOT / "eval" / "datasets" / "golden.jsonl"
REPORTS = ROOT / "eval" / "reports"
BASELINES = ROOT / "eval" / "baselines"


def load_golden(path: Path = GOLDEN) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def evaluate(
    rows: list[dict],
    answerer: Answerer,
    *,
    k: int,
    pause_s: float = 0.0,
    retries: int = 2,
    retry_wait_s: float = 5.0,
    clock: Callable[[], float] = time.perf_counter,
) -> list[QuestionResult]:
    """Ask every question through the API; record what was retrieved, the answer, and the time."""
    app = create_app(build=lambda: answerer, health_check=lambda: None)
    results = []
    with TestClient(app) as client:
        for row in rows:
            hits = answerer.retrieve(row["question"])  # what the LLM sees (reranked if on)
            retrieved = [f"{hit.chunk.doc_id}:{hit.chunk.page}" for hit in hits]
            start = clock()
            body = _ask(client, row["question"], retries, retry_wait_s)
            latency = clock() - start
            results.append(
                QuestionResult(
                    id=row["id"],
                    answerable=row["answerable"],
                    expected_sources=row["expected_sources"],
                    key_facts=row["key_facts"],
                    retrieved=retrieved,
                    status=body["status"] if body else "error",
                    answer=body["answer"] if body else "",
                    latency_s=round(latency, 3),
                )
            )
            time.sleep(pause_s)
    return results


def _ask(client: TestClient, question: str, retries: int, wait_s: float) -> dict | None:
    for attempt in range(retries + 1):
        response = client.post("/v1/ask", json={"question": question})
        if response.status_code == 200:
            return response.json()
        if attempt < retries:
            time.sleep(wait_s)
    return None


def build_report(results: list[QuestionResult], settings: Settings) -> dict:
    return {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "config": {
            "chat_model": settings.chat_model,
            "chat_temperature": settings.chat_temperature,
            "embedding_model": settings.embedding_model,
            "prompt_version": PROMPT_VERSION,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap,
            "top_k": settings.top_k,
            "retriever": "postgres",
            "retrieval_mode": settings.retrieval_mode,
            "candidates": settings.candidates,
            "rerank": settings.rerank,
            "reranker_model": settings.reranker_model if settings.rerank else None,
            "rerank_threshold": settings.rerank_threshold if settings.rerank else None,
        },
        "summary": summarise(results, k=settings.top_k),
        "errors": sum(r.status == "error" for r in results),
        "results": [asdict(r) for r in results],
    }


def write_report(report: dict, folder: Path = REPORTS) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    stamp = report["created_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    path = folder / f"{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return path


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT
        )
    except OSError:
        return None
    return out.stdout.strip() or None


def _print(results: list[QuestionResult], report: dict, k: int) -> None:
    print(f"{'id':4} {'ok':2} {'status':9} {'recall':>6} {'rr':>5} {'facts':>5} {'secs':>5}")
    for r in results:
        ok = "✅" if r.status == ("answered" if r.answerable else "no_answer") else "❌"
        if r.answerable:
            recall = f"{recall_at_k(r.expected_sources, r.retrieved, k):.2f}"
            rr = f"{reciprocal_rank(r.expected_sources, r.retrieved):.2f}"
            facts = f"{key_fact_score(r.answer, r.key_facts):.2f}"
        else:
            recall = rr = facts = "-"
        print(f"{r.id:4} {ok} {r.status:9} {recall:>6} {rr:>5} {facts:>5} {r.latency_s:5.1f}")
    print()
    for name, value in report["summary"].items():
        print(f"  {name:20} {value:.3f}" if isinstance(value, float) else f"  {name:20} {value}")
    print(f"  {'errors':20} {report['errors']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run", description=__doc__.split("\n")[0])
    parser.add_argument(
        "--save-baseline", metavar="NAME", help="also write eval/baselines/NAME.json (committed)"
    )
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between questions")
    args = parser.parse_args(argv)

    settings = get_settings()
    answerer = build_db_answerer(settings)
    results = evaluate(load_golden(), answerer, k=settings.top_k, pause_s=args.pause)
    report = build_report(results, settings)

    _print(results, report, settings.top_k)
    print(f"\nreport: {write_report(report).relative_to(ROOT)}")
    if args.save_baseline:
        baseline = BASELINES / f"{args.save_baseline}.json"
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"baseline: {baseline.relative_to(ROOT)}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
