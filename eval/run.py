"""Run the golden set through the API and score it (spec 02 step 8, ISS-026).

    uv run python -m eval.run                          # report → eval/reports/<time>.json
    uv run python -m eval.run --save-baseline phase7   # also → eval/baselines/phase7.json
    uv run python -m eval.run --no-judge               # skip the eval judge (no extra calls)
    uv run python -m eval.run --judge-report PATH      # judge a finished run (no generator calls)

Retrieval settings come from the environment, e.g. RETRIEVAL_MODE=hybrid RERANK=true.

Answers go through the real API in-process (FastAPI test client), with the real models and the
database; retrieval metrics come from the same answerer's retriever, since the API doesn't return
chunks. Free-tier models sometimes refuse a burst of calls, so a failed request is retried.

Phase 7 (spec 07 D4): a capturing recorder keeps each request's full result (token usage, the
chunks the LLM actually saw); the pinned eval judge scores correctness and faithfulness; tokens
become a list-price cost per query (`eval/thresholds.yaml`).
"""

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from langchain.chat_models import init_chat_model

from app.answering.answer import PROMPT_VERSION, Answerer, build_db_answerer
from app.audit.recorder import NullRecorder
from app.config import ROOT, Settings, get_settings
from app.domain import AnswerResult, User
from app.main import create_app
from eval.judges import CORRECTNESS, FAITHFULNESS, EvalJudge
from eval.metrics import (
    QuestionResult,
    cost_per_query,
    judged_scores,
    key_fact_score,
    recall_at_k,
    reciprocal_rank,
    summarise,
)

GOLDEN = ROOT / "eval" / "datasets" / "golden.jsonl"
REPORTS = ROOT / "eval" / "reports"
BASELINES = ROOT / "eval" / "baselines"


class CapturingRecorder(NullRecorder):
    """Stores nothing, but keeps each finished request's full result for the eval."""

    def __init__(self) -> None:
        self.results: dict[str, AnswerResult] = {}

    def finish(self, request_id: str, user: User, result: AnswerResult, **kwargs) -> None:
        self.results[request_id] = result


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
    judge: EvalJudge | None = None,
) -> list[QuestionResult]:
    """Ask every question through the API; record what was retrieved, the answer, and the time."""
    scope = getattr(answerer.index, "default_scope", None)  # Postgres: settings tenant + roles
    user = User(
        id="eval",
        tenant_id=scope.tenant_id if scope else "",
        email="eval@localhost",
        roles=scope.roles if scope else [],
        permissions=[],
    )
    captured = CapturingRecorder()  # quality runs aren't user requests: nothing is stored
    app = create_app(
        recorder=lambda: captured,
        build=lambda: answerer,
        health_check=lambda: None,
        authenticator=lambda: lambda _: user,
    )
    results, answered = [], []
    with TestClient(app, headers={"Authorization": "Bearer eval"}) as client:
        for row in rows:
            hits = answerer.retrieve(row["question"])  # what the LLM sees (reranked if on)
            retrieved = [f"{hit.chunk.doc_id}:{hit.chunk.page}" for hit in hits]
            start = clock()
            body = _ask(client, row["question"], retries, retry_wait_s)
            latency = clock() - start
            full = captured.results.get(body["request_id"]) if body else None
            answered.append(full)
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
                    usage=full.usage if full else {},
                )
            )
            time.sleep(pause_s)
    if judge is None:
        return results
    # Judge only after every question is answered: the judge shares the provider's rate limit with
    # the system's own grounding judge, and must never slow down or fail what it measures.
    for i, (row, full) in enumerate(zip(rows, answered, strict=True)):
        if full is None or full.status != "answered":
            continue
        correctness = None
        if row["answerable"]:
            correctness = judge.correctness(row["question"], row["expected_answer"], full.answer)
        faithfulness = judge.faithfulness(full.answer, [h.chunk.text for h in full.retrieved])
        results[i] = replace(results[i], correctness=correctness, faithfulness=faithfulness)
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


def seen_texts(answerer: Answerer, question: str) -> list[str]:
    """What the LLM read for this question: the retrieved chunks after the context guard (masked,
    injections dropped). Retrieval and the guard are deterministic, so a past run's view can be
    rebuilt without calling the generator again."""
    scope = getattr(answerer.index, "default_scope", None)
    hits = answerer.retrieve(question, scope)
    if answerer.context_guard is not None:
        hits, _ = answerer.context_guard.check(hits, scope)
    return [hit.chunk.text for hit in hits]


def judge_report(
    report: dict,
    rows: list[dict],
    answerer: Answerer,
    judge: EvalJudge,
    settings: Settings,
    pause_s: float = 0.0,
) -> dict:
    """Score a finished run with the eval judge, then recompute its summary."""
    by_id = {row["id"]: row for row in rows}
    results = []
    for saved in report["results"]:
        result, row = QuestionResult(**saved), by_id[saved["id"]]
        if result.status == "answered":
            correctness = None
            if result.answerable:
                correctness = judge.correctness(
                    row["question"], row["expected_answer"], result.answer
                )
            texts = seen_texts(answerer, row["question"])
            result = replace(
                result,
                correctness=correctness,
                faithfulness=judge.faithfulness(result.answer, texts),
            )
            time.sleep(pause_s)
        results.append(result)
    summary = summarise(results, k=settings.top_k) | judged_scores(results)
    summary |= cost_per_query(results, load_prices())
    config = {
        **report["config"],
        "eval_judge_model": settings.eval_judge_model,
        "eval_judge_prompts": [CORRECTNESS, FAITHFULNESS],
    }
    judged_at = datetime.now(UTC).isoformat(timespec="seconds")
    return {
        **report,
        "config": config,
        "judged_at": judged_at,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }


def load_prices() -> dict:
    return yaml.safe_load((ROOT / "eval" / "thresholds.yaml").read_text(encoding="utf-8"))["prices"]


def build_report(results: list[QuestionResult], settings: Settings, judged: bool = True) -> dict:
    summary = summarise(results, k=settings.top_k)
    if judged:
        summary |= judged_scores(results)
    summary |= cost_per_query(results, load_prices())
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
            "judge_model": settings.judge_model,
            "input_guard": settings.input_guard,
            "context_guard": settings.context_guard,
            "grounding_judge": settings.grounding_judge,
            "injection_threshold": settings.injection_threshold,
            "eval_judge_model": settings.eval_judge_model if judged else None,
            "eval_judge_prompts": [CORRECTNESS, FAITHFULNESS] if judged else None,
        },
        "summary": summary,
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
        print(f"  {name:20} {value:.6g}" if isinstance(value, float) else f"  {name:20} {value}")
    print(f"  {'errors':20} {report['errors']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m eval.run", description=__doc__.split("\n")[0])
    parser.add_argument(
        "--save-baseline", metavar="NAME", help="also write eval/baselines/NAME.json (committed)"
    )
    parser.add_argument("--pause", type=float, default=1.0, help="seconds between questions")
    parser.add_argument("--no-judge", action="store_true", help="skip correctness/faithfulness")
    parser.add_argument("--judge-report", metavar="PATH", help="judge a finished run's report")
    parser.add_argument(
        "--retry-wait",
        type=float,
        default=20.0,
        help="seconds before retrying a failed question (provider rate limits)",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    answerer = build_db_answerer(settings)
    judge = None
    if not args.no_judge:
        model = init_chat_model(settings.eval_judge_model, temperature=0, timeout=60)
        judge = EvalJudge(model)
    if args.judge_report:
        if judge is None:
            parser.error("--judge-report needs the judge (drop --no-judge)")
        saved = json.loads(Path(args.judge_report).read_text(encoding="utf-8"))
        report = judge_report(saved, load_golden(), answerer, judge, settings, args.pause)
        results = [QuestionResult(**r) for r in report["results"]]
    else:
        results = evaluate(
            load_golden(),
            answerer,
            k=settings.top_k,
            pause_s=args.pause,
            judge=judge,
            retry_wait_s=args.retry_wait,
        )
        report = build_report(results, settings, judged=judge is not None)

    _print(results, report, settings.top_k)
    print(f"\nreport: {write_report(report).relative_to(ROOT)}")
    if args.save_baseline and report["errors"]:
        print(
            f"baseline NOT saved: {report['errors']} questions failed (a baseline must be complete)"
        )
    elif args.save_baseline:
        baseline = BASELINES / f"{args.save_baseline}.json"
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"baseline: {baseline.relative_to(ROOT)}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
