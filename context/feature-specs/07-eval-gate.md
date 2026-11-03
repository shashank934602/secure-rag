# 07 — Full evaluation and the CI gate

## Goal

Turn "it seems better" into numbers a change must meet. Grow the security sets to 300+ cases each, measure quality and
security with confidence intervals, pin every model the numbers depend on, and run it all in GitHub Actions so a change that
weakens a guard fails automatically. Every run produces a JSON report, an HTML report, and a diff against the baseline.
**Done when** a change that weakens a guard is automatically blocked (its CI run fails, naming the regression).

## Decisions (2026-11-03 — recommended options taken, "build now, study later")

| # | Decision |
|---|----------|
| D1 | **Datasets.** `adversarial.jsonl` ≥ 300 own attacks in 7 categories; `benign.jsonl` ≥ 300 questions (plain, *hard* ones using attackers' words, multilingual); `indirect.jsonl` ≥ 100 document passages (attacks hidden in document text, and benign passages with instruction-like wording) for the context guard; plus a **public slice**: the `deepset/prompt-injections` test split (116 rows, Apache-2.0), reported separately and not gated, because public sets may overlap the classifier's training data (*contamination*) and use different labels. Cases were written without running the guard on them. |
| D2 | **Dev/test split.** Each case is assigned `dev` (30%) or `test` (70%) by a hash of its id, so the split is stable and needs no field. Tuning (ISS-048) may only look at `dev`; the gate reads `test`. |
| D3 | **Security metrics** (`python -m eval.security`, offline, local models only): input guard block rate and false refusal rate with 95% Wilson intervals, per category; context guard drop rate on attack passages, false drops on benign passages **and on every real corpus chunk**. Deterministic: same code and model → same verdicts. |
| D4 | **Quality metrics** (`python -m eval.run`, real models): recall@5, MRR, key-fact score, No-Answer accuracy (as before), plus **correctness** and **faithfulness** scored by a pinned eval judge (D6), p50/p95 latency, tokens and **cost per query** (token usage × list prices in `thresholds.yaml`). `eval.leakage` must find 0 leaks. The ACL-change check is the `tests/test_acl.py` database tests (hard fail in CI). |
| D5 | **Gate rules** (`python -m eval.gate`), in `eval/thresholds.yaml`: (a) **hard fails**: any leak; an attack the baseline blocked that now passes (*per-case regression*); a pinned model that differs from the configuration; (b) **floors and ceilings** per metric, set from the current baseline minus a small tolerance (a *ratchet*: raise them when the system improves, never lower them silently); (c) the architecture's **targets** (block ≥ 95%, false refusals ≤ 5%, recall@5 ≥ 0.85…) are reported as met/missed but don't fail CI until reached. Benign cases newly refused are warnings, bounded by the ceiling. |
| D6 | **Pinned models** in `thresholds.yaml`: generator, embeddings, guard judge, eval judge, injection classifier, reranker. Dated ids, not `-latest`: the guard judge moves to `ministral-8b-2512`; the eval judge is `mistral-small-2603` (a different model from the guard judge, so the guard isn't grading itself). Changing a pin means re-baselining. |
| D7 | **Reports.** Each gate run writes `eval/reports/gate-*.json` and `.html` (metrics, intervals, thresholds, met/missed, diff vs baseline, per-case regressions) and, in CI, a Markdown summary on the run page and the HTML as an artifact. |
| D8 | **CI** (`.github/workflows/ci.yml`): on every push and pull request: lint + offline tests; database tests (Postgres in a throwaway container, includes RLS and ACL-change); the **security gate** (local models, cached). The **quality gate** (real models, needs `GROQ_API_KEY` and `MISTRAL_API_KEY` repository secrets and ingests the corpus into a CI database) runs when the secrets exist and the change touches `app/`, `eval/`, `prompts/`, or `data/`; without secrets it reports "skipped" rather than failing. Linux CI installs the CPU build of PyTorch. |
| D9 | **Own judge prompts instead of the RAGAS library**: the same method (split the answer into claims; check each against the retrieved text / the expected answer), in two short versioned prompts we can read and test, run on the free tier with few calls. RAGAS stays the reference for the idea. |

## Slices

| Slice | Issue | What |
|-------|-------|------|
| S1 | ISS-059 | Datasets to 300+ each, indirect passages, public slice, hash split; `eval.security` (input + context guard); security baseline |
| S2 | ISS-060 | `eval/thresholds.yaml` (pins, floors, targets), `eval.gate` with per-case regressions, HTML + Markdown report with diff |
| S3 | ISS-061 | Quality: token usage and cost per query, judge correctness + faithfulness, quality baseline and gate |
| S4 | ISS-062 | GitHub Actions; a demo change weakening a guard is blocked; lesson; tester; release `v0.7.0` |

## Scope limits

- No guard tuning in this phase (ISS-048 uses the `dev` split later); the numbers are measured, not improved.
- Requiring the check before merging (branch protection) is a repository setting the owner turns on (ISS-063); the gate itself fails the run.
- No human feedback loop into the golden set (`/v1/feedback`, architecture §8) yet.

## Check when done

- `adversarial` ≥ 300, `benign` ≥ 300, `indirect` ≥ 100; every rate in the report has a 95% interval.
- `eval.gate` exits non-zero on a weakened guard (tested offline with a fake classifier, and for real on a demo branch in CI).
- Every pinned model matches the configuration; the HTML report shows the diff against the committed baseline.
- CI is green on `main`; the tester's report is in `docs/test-reports/`.
