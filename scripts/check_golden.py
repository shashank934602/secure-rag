"""Check the golden set against the corpus (spec 02 step 6, ISS-024).

    uv run python -m scripts.check_golden

A wrong test question makes a correct answer look wrong, so every entry is checked:
unique id; answerable entries have sources and key facts, and every key fact appears on one of
its expected pages; unanswerable entries expect exactly the No-Answer sentence; counts 14 / 6.
"""

import json
import sys
from pathlib import Path

from app.answering.answer import NO_ANSWER
from app.config import ROOT
from app.ingestion.loaders import load_pages
from eval.metrics import normalise

ANSWERABLE, UNANSWERABLE = 14, 6


def check(dataset: Path, corpus: Path) -> list[str]:
    """Every problem found, as one readable line each; an empty list means the set is valid."""
    pages = {f"{p.doc_id}:{p.page}": normalise(p.text) for p in load_pages(corpus)}
    rows = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    errors: list[str] = []
    seen: set[str] = set()

    for row in rows:
        rid = row["id"]
        if rid in seen:
            errors.append(f"{rid}: duplicate id")
        seen.add(rid)
        sources, facts = row["expected_sources"], row.get("key_facts", [])

        if not row["answerable"]:
            if row["expected_answer"] != NO_ANSWER or sources or facts:
                errors.append(f"{rid}: unanswerable must expect only the No-Answer sentence")
            continue

        if not sources or not facts:
            errors.append(f"{rid}: answerable needs expected_sources and key_facts")
        for source in sources:
            if source not in pages:
                errors.append(f"{rid}: source {source} is not a page in the corpus")
        for fact in facts:
            if not any(normalise(fact) in pages.get(s, "") for s in sources):
                errors.append(f"{rid}: key fact {fact!r} is not on any of {sources}")

    answerable = sum(r["answerable"] for r in rows)
    if (answerable, len(rows) - answerable) != (ANSWERABLE, UNANSWERABLE):
        errors.append(
            f"counts: {answerable} answerable / {len(rows) - answerable} unanswerable, "
            f"expected {ANSWERABLE} / {UNANSWERABLE}"
        )
    return errors


def main() -> int:
    dataset = ROOT / "eval" / "datasets" / "golden.jsonl"
    errors = check(dataset, ROOT / "data" / "sample")
    for error in errors:
        print(error)
    if errors:
        return 1
    count = sum(1 for line in dataset.read_text().splitlines() if line.strip())
    print(f"golden set OK: {count} questions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
