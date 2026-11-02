# 05 — Guardrails

## Goal

Add the guards around the answering flow, each assuming the one before it can fail (defense in depth): an **input guard**
that refuses prompt-injection attempts, a **context guard** that drops injected chunks and masks sensitive personal data,
**output checks** that strip exfiltration channels and redact secrets, and a **grounding judge** that rejects answers
their sources don't support. Every guard **fails closed**. Measure an early **block rate** and **false-refusal rate** on new
adversarial and benign sets, and show the golden set doesn't regress.

## Decisions (2026-11-02 — recommended options taken, learner chose "build now, study later")

| # | Decision |
|---|----------|
| D1 | **Input guard** = local classifier `protectai/deberta-v3-base-prompt-injection-v2` (labels SAFE / INJECTION) **or** pattern rules (e.g. "ignore … instructions/rules", "system prompt", "you are now", "list every document"). Either one blocks → **Refusal**: status `refused`, fixed message, no retrieval, no LLM call (closes ISS-041). |
| D2 | **Indirect injection**: ingest scans every chunk with the same classifier in 512-token windows; a flagged document is **quarantined** (`documents.status = 'quarantined'`, its chunks `is_active = false`) and reported. At query time the **context guard** re-checks the retrieved chunks and drops flagged ones (defense in depth for chunks ingested before the scanner existed). |
| D3 | **Personal data**: our own pattern detector (`app/guards/pii.py`) instead of Presidio, for an allow-list of *sensitive* types: `IBAN` (checksum), `UK_BANK_ACCOUNT` (sort code + account), `UK_NINO`, `CREDIT_CARD` (Luhn), `UK_MOBILE`, `PERSONAL_EMAIL` (consumer domains). Work emails and desk phones are **directory information** employees need (g05, g06, g17), so they are not masked. Detected types are stored per chunk (`chunks.pii_types`); text stays raw (ADR-0004). Why not Presidio: every type on our list is pattern-based anyway, and Presidio would add a spaCy model (~600 MB) for no gain at this stage. |
| D4 | **Masking**: users without the `pii:read` permission get those values replaced by `[IBAN]`, `[UK_NINO]`, … in the chunks **before the LLM sees them**, and again in the answer. Harriet gets `pii:read` (migration `0004`). Test data: `data/tenants/aldermoor-finance/expense-payees.md`, a payee list uploaded by mistake with fake bank details, visible to employees. |
| D5 | **Output checks** (structural, Invariant 3): remove URLs, markdown links/images, and HTML from the answer; redact secrets (API-key and private-key patterns) for everyone and personal data for users without `pii:read`. Citation validity stays as in Phase 3. |
| D6 | **Grounding judge**: a model from a **different family** than the generator (Groq `gpt-oss-120b`): Mistral `ministral-8b-latest`. It reads the cited chunks and the answer and returns `grounded: true/false` with the unsupported claims. Ungrounded → one retry (shared with the citation retry, `MAX_ATTEMPTS = 2`) → No-Answer. |
| D7 | **Fail closed** (Invariant 4): if the classifier can't load or run, or the judge errors or times out (15 s), the request is refused with status `error` (API: 503). No guard is ever skipped. |
| D8 | **Graph**: `input_guard → retrieve → context_guard → generate → output_checks → check_citations → grounding_judge`, with edges to `refused`, `no_answer`, and one retry. `AnswerResult.status` gains `refused`. |
| D9 | **Sets**: `eval/datasets/adversarial.jsonl` (~50: direct injections, jailbreaks, exfiltration and data-dump requests) and `eval/datasets/benign.jsonl` (~50 ordinary and tricky-but-benign questions). `python -m eval.guards` reports the block rate and false-refusal rate with **95% Wilson intervals**. Early numbers only; the full gate is Phase 7. |
| D10 | The input guard runs on every question, so the golden set must show **no false refusals** (re-run `eval.run`), and leakage must stay at 0. |

## Slices

| Slice | Issue | What |
|-------|-------|------|
| S1 | ISS-042 | Injection classifier, pattern rules, input guard → Refusal; adversarial + benign sets; `eval.guards` |
| S2 | ISS-043 | Ingest scan + quarantine, context guard; PII detector, `pii_types`, masking by permission; migration `0004` |
| S3 | ISS-044 | Output checks: strip links/images/HTML, redact secrets and PII |
| S4 | ISS-045 | Grounding judge (Mistral), retry, fail closed |
| S5 | ISS-046 | Numbers (guards, golden, leakage), lesson, release `v0.5.0` |

## Scope limits

- No audit tables (Phase 6): guard verdicts are kept in the graph state and returned in debug output only.
- No HMAC of queries or log redaction pipeline beyond what exists (Phase 6). No CI gate (Phase 7).
- The poisoning case (a false but well-formed document, ISS-019) is **not** solved by these guards: it is grounded.

## Check when done

- Each guard has tests, including a fail-closed test for each model-backed guard.
- `eval.guards`: block rate and false-refusal rate recorded with intervals.
- The golden set: 0 false refusals from the input guard; scores not worse than Phase 4.
- `eval.leakage`: 0 leaks. The bluff "CEO earns £200,000 [expense-policy:1]" is rejected by the grounding judge.
