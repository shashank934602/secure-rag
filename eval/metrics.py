"""Eval metrics (spec 02 step 7, ISS-025). Pure functions: no models, no database.

Pages are written "doc_id:page", and `retrieved` lists the page of each retrieved chunk in rank
order (the same page can appear twice when two of its chunks were retrieved).
"""

import re
from dataclasses import dataclass, field
from statistics import mean

# Characters real models write that look like plain spaces or hyphens but aren't.
_SPACES = dict.fromkeys(map(ord, "    "), " ")
_HYPHENS = dict.fromkeys(map(ord, "‐‑‒–—−"), "-")


@dataclass(frozen=True)
class QuestionResult:
    """One golden question after a run: what was expected and what the system did."""

    id: str
    answerable: bool
    expected_sources: list[str]
    key_facts: list[str]
    retrieved: list[str]
    status: str
    answer: str
    latency_s: float
    correctness: float | None = None  # eval judge vs the expected answer (Phase 7)
    faithfulness: float | None = None  # eval judge: claims supported by what the LLM saw
    usage: dict[str, dict[str, int]] = field(default_factory=dict)  # model → token counts


def recall_at_k(expected: list[str], retrieved: list[str], k: int = 5) -> float:
    """Share of the expected pages that appear among the top k retrieved."""
    if not expected:
        raise ValueError("recall needs expected pages (unanswerable questions have none)")
    top = set(retrieved[:k])
    return sum(page in top for page in set(expected)) / len(set(expected))


def reciprocal_rank(expected: list[str], retrieved: list[str]) -> float:
    """1 / (1-based position of the first expected page), or 0 if none was retrieved."""
    for position, page in enumerate(retrieved, start=1):
        if page in expected:
            return 1 / position
    return 0.0


def normalise(text: str) -> str:
    """Lowercase; drop **bold** markers; unusual spaces and hyphens become plain ones;
    collapse whitespace. Used on both the answer and the key fact before comparing."""
    text = text.translate(_SPACES).translate(_HYPHENS).replace("*", "")
    return re.sub(r"\s+", " ", text).strip().lower()


def key_fact_score(answer: str, key_facts: list[str]) -> float:
    """Share of the key facts that appear in the answer (after normalising both)."""
    if not key_facts:
        raise ValueError("key_fact_score needs key facts (unanswerable questions have none)")
    text = normalise(answer)
    return sum(normalise(fact) in text for fact in key_facts) / len(key_facts)


def no_answer_correct(status: str, answerable: bool) -> bool:
    """True when the system said "I don't know" exactly when it should have."""
    return status == ("answered" if answerable else "no_answer")


def percentile(values: list[float], p: float) -> float:
    """The p-th percentile (0–100), interpolating linearly between the two nearest values."""
    if not values:
        raise ValueError("percentile of no values")
    if not 0 <= p <= 100:
        raise ValueError(f"percentile must be between 0 and 100, got {p}")
    ordered = sorted(values)
    rank = p / 100 * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (rank - low) * (ordered[high] - ordered[low])


def summarise(results: list[QuestionResult], k: int = 5) -> dict[str, float | int]:
    """The run's headline numbers. Retrieval and key facts are averaged over answerable questions
    only (a refused answerable question scores 0 on key facts); No-Answer accuracy is over the
    unanswerable ones; latency covers every question."""
    answerable = [r for r in results if r.answerable]
    unanswerable = [r for r in results if not r.answerable]
    latencies = [r.latency_s for r in results]
    return {
        "questions": len(results),
        "answerable": len(answerable),
        "unanswerable": len(unanswerable),
        "recall_at_5": mean(recall_at_k(r.expected_sources, r.retrieved, k) for r in answerable),
        "mrr": mean(reciprocal_rank(r.expected_sources, r.retrieved) for r in answerable),
        "key_fact_score": mean(key_fact_score(r.answer, r.key_facts) for r in answerable),
        "answered_rate": mean(r.status == "answered" for r in answerable),
        "false_refusals": sum(r.status == "no_answer" for r in answerable),
        "no_answer_accuracy": mean(r.status == "no_answer" for r in unanswerable),
        "latency_p50_s": percentile(latencies, 50),
        "latency_p95_s": percentile(latencies, 95),
    }


def judged_scores(results: list[QuestionResult]) -> dict[str, float | int | None]:
    """Correctness over answerable questions (one not answered scores 0) and faithfulness over
    answered ones; questions the judge couldn't score are counted, not guessed."""
    answerable = [r for r in results if r.answerable]
    correctness = [0.0 if r.status != "answered" else r.correctness for r in answerable]
    faithful = [r.faithfulness for r in results if r.status == "answered"]
    scored_c = [c for c in correctness if c is not None]
    scored_f = [f for f in faithful if f is not None]
    judged_any = any(r.correctness is not None for r in answerable if r.status == "answered")
    return {
        # Not-answered zeros alone aren't a correctness score: unknown until the judge scored one.
        "correctness": mean(scored_c) if judged_any else None,
        "faithfulness": mean(scored_f) if scored_f else None,
        "judge_unscored": correctness.count(None) + faithful.count(None),
    }


def cost_per_query(results: list[QuestionResult], prices: dict[str, dict[str, float]]) -> dict:
    """Average tokens and list-price cost per question. Prices are USD per million tokens, keyed
    `provider:model`; providers report the model without the provider, so match on that part."""
    by_model = {key.split(":", 1)[-1]: price for key, price in prices.items()}
    tokens = cost = 0.0
    unpriced = set()
    for r in results:
        for model, counts in r.usage.items():
            tokens += counts.get("total_tokens", 0)
            price = by_model.get(model)
            if price is None:
                unpriced.add(model)
                continue
            cost += (counts.get("input_tokens", 0) * price["input"]
                     + counts.get("output_tokens", 0) * price["output"]) / 1_000_000  # fmt: skip
    n = max(len(results), 1)
    return {"tokens_per_query": round(tokens / n, 1), "cost_per_query_usd": round(cost / n, 6),
            "unpriced_models": sorted(unpriced)}  # fmt: skip


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a rate (Wilson score). With few cases it stays wide:
    50/50 blocked means "at least about 93%", not "100%"."""
    if n <= 0:
        raise ValueError("wilson_interval needs at least one case")
    p = successes / n
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    margin = z * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)
