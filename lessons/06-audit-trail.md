# Lesson 6 — The audit trail: explaining every answer after the fact

> Phase 6, built at pace (build now, study later). Spec: `context/feature-specs/06-audit-observability.md`.
> Every result here is real, from 2026-11-03.

## Why

Regulated companies must answer "**why did the system say that?**" weeks later, and prove the record wasn't altered.
Phase 6 makes every answer explainable and every record tamper-evident.

```
question ─▶ request record (status "started", HMAC + redacted text) ─▶ graph runs ─▶ ONE transaction:
                                                                                   status, redacted answer,
                                                                                   sources, every decision,
                                                                                   per-step timings
auditor ─▶ GET /v1/audit/requests/{id} · /v1/audit/requests?… · /v1/audit/verify   (reads audited too)
```

## S1 — A hash chain (ISS-050)

Each audit event stores `prev_hash` (the previous event's hash) and `row_hash` = SHA-256(prev_hash + the event's content in a
fixed JSON form). The first event's `prev_hash` is 64 zeros.

- **Edit** a past event → its content no longer matches its hash.
- Edit it **and recompute** its hash → the *next* event still points at the old hash (the smart attacker is caught too).
- **Delete** one → a gap in the numbering (`seq`).

`verify` recomputes the chain and names the first broken event. **Append-only**: database triggers refuse UPDATE, DELETE, and
TRUNCATE for *every* role, the admin included; only someone who switches the triggers off (a superuser) could change history,
and `verify` then catches it. Tested: edit of #3 → "broken at 3"; deletion of #2 → "gap at 3".

**Concurrency**: two requests appending at once could both read "last seq = 41" and both write 42, forking the chain. A
per-tenant **advisory lock** makes appends take turns. Tested: 4 writers × 10 events → 40 events, chain intact.

Each tenant has its **own chain**, invisible to others (row-level security).

## S2 — Recording without storing secrets (ISS-051)

- **Request record first**: written on arrival (status `started`), so even a crash leaves a trace.
- **No raw text at rest** (Invariant 5): the question is stored as an **HMAC** (a *keyed* hash: the same question gives the same
  value, so repeats can be found, but without the key nobody can test guesses) plus a **redacted** copy. Real check: Alice typed
  her IBAN; **0 rows** anywhere contain it.
- **One transaction** for status, answer, sources, decisions, timings: all or nothing.
- **Fail closed**: if the audit can't be written, the question isn't answered (503), and the model is never even called.
- **Access changes** are audited *inside the change's own transaction*: if the audit fails, the change rolls back.
- Sources are stored as text references (`doc:page:index`), so re-ingesting a document never erases what old answers used.

**What the log revealed:** an "I don't know" that looked like a bug was the grounding judge rejecting an answer twice, because
two of our documents **disagree** (the expense policy says reimbursements are "paid with the next monthly salary"; the payee
file says "bank transfer within 5 working days"). A real conflicting-documents case (ISS-019) that only the audit made visible.

## S3 — The auditor's view (ISS-052)

Only users with the `auditor` permission (Audrey). Open a request and see its sources and every decision in order; search by
status, user, time; `/verify` the chain. Another tenant's request is a 404. **Reading the audit is itself audited**
(`audit_read`), because who looked at what matters too.

## S4 — Seeing where the time goes (ISS-053)

Every graph step is timed, and each request writes **one JSON log line** (who, outcome, total time, time per step; never the
question). The first such line exposed a **cold start**: the model wrote in 0.75 s, but loading the local classifier and
reranker on the first request cost ~12 s. Loading them at start-up took the first request from **14.8 s to 3.8 s** that day.
The tester later saw no cold-start penalty at all (first request 6.0 s, second 6.3 s): the warm-up works, but the total is
now dominated by the free-tier model (1–12 s per call). Re-measured after a fresh restart: first request 4.5 s, second
3.3 s. An honest number names its conditions.

Deferred: self-hosted Langfuse (ISS-054), about six services; the concepts (spans, timings, redaction) are covered.

## What the independent tester found

Verdict: release with known issues, no critical or high (`docs/test-reports/v0.6.0.md`). Fixed before release, each with a
test that failed on the old code:

- **Chunked uploads skipped the size limit** (T-1). The check read the declared `Content-Length`; a client can send
  `Transfer-Encoding: chunked`, which declares no length. Fix: count bytes as they arrive and stop at 16 KB. Lesson: check
  what is *received*, not what is *claimed*.
- **Failures were the least explained requests** (T-2). A rate-limited request kept only START and ERROR. Fix: a failing step
  attaches its progress to the error (decisions so far, sources, timings, which step failed), and the audit records it.
- **"Who tried to look" was missing** (T-4): denied or not-found audit reads are now recorded too.
- **Silence is ambiguous** (T-5): a guard that changed nothing now records PASS, so "ran and allowed" differs from "didn't run".

Logged for later: NI numbers with an invalid prefix aren't masked (ISS-057); one HMAC key for all tenants (ISS-058).

## Explain it back (later)

1. Why does editing one old event break the chain, even if the attacker recomputes that event's hash?
2. Why is the question stored as an HMAC and not a plain hash, and not as text?
3. Why refuse to answer when the audit can't be written?
4. Why record auditors' reads?
5. What did per-step timings reveal that the total time couldn't?
6. Why is a body-size check on `Content-Length` alone not enough?
7. Why should a *failed* request be recorded in more detail, not less?
