"""Early guard numbers (spec 05 D9, ISS-042): block rate on attacks, false refusals on benign.

    uv run python -m eval.guards

Runs the real input guard (rules + local classifier) over eval/datasets/adversarial.jsonl and
eval/datasets/benign.jsonl. Rates come with 95% Wilson intervals: with 50 cases, the error bars
are wide, so read "the interval" not "the number". The full gate comes in Phase 7.
"""

import json
import sys
import time
from collections import Counter, defaultdict

from app.config import ROOT, get_settings
from app.guards.injection import DebertaInjectionClassifier, InputGuard
from eval.metrics import wilson_interval

DATASETS = ROOT / "eval" / "datasets"


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATASETS / name).read_text().splitlines() if line.strip()]


def _rate(hits: int, n: int) -> str:
    low, high = wilson_interval(hits, n)
    return f"{hits}/{n} = {hits / n:.0%}  (95% CI {low:.0%}–{high:.0%})"


def main() -> int:
    guard = InputGuard(DebertaInjectionClassifier(), get_settings().injection_threshold)
    rows = []
    for kind, name in (("adversarial", "adversarial.jsonl"), ("benign", "benign.jsonl")):
        for item in _load(name):
            verdict = guard.check(item["text"])
            rows.append({**item, "kind": kind, "blocked": verdict.decision == "BLOCK",
                         "reason": verdict.reason, "score": verdict.score})  # fmt: skip

    attacks = [r for r in rows if r["kind"] == "adversarial"]
    benign = [r for r in rows if r["kind"] == "benign"]
    blocked, refused = sum(r["blocked"] for r in attacks), sum(r["blocked"] for r in benign)

    print(f"block rate (attacks):     {_rate(blocked, len(attacks))}")
    print(f"false refusals (benign):  {_rate(refused, len(benign))}")
    by_category = defaultdict(list)
    for r in attacks:
        by_category[r["category"]].append(r["blocked"])
    print("\nblocked by category:")
    for category, hits in by_category.items():
        print(f"  {category:18} {sum(hits)}/{len(hits)}")
    reasons = Counter(r["reason"].split(":")[0] for r in attacks if r["blocked"])
    print(
        f"\nwho caught the attacks:  rules {reasons['rule']} · classifier {reasons['classifier']}"
    )
    print("\nmissed attacks:")
    for r in attacks:
        if not r["blocked"]:
            print(f"  {r['id']} [{r['category']}] score {r['score']}: {r['text'][:80]}")
    print("\nfalse refusals:")
    for r in benign:
        if r["blocked"]:
            print(f"  {r['id']} ({r['reason']}): {r['text'][:80]}")

    out = ROOT / "eval" / "reports" / f"guards-{time.strftime('%Y%m%dT%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {"blocked": blocked, "attacks": len(attacks), "false_refusals": refused,
               "benign": len(benign)}  # fmt: skip
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False))
    print(f"\nreport: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
