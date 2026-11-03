# 06 — Audit trail and observability

## Goal

Make every answer explainable after the fact. Each request is recorded **at the start**, every guard verdict and stage
outcome is appended to a **hash-chained, append-only** audit log, and an auditor can open any request, search them, and run
`/verify` to prove nothing was edited or deleted. Add lightweight tracing: per-step timings and structured, redacted logs.
**Done when** any request can be opened with every decision visible, and tampering with a row is detected by `/verify`.

## Decisions (2026-11-03 — recommended options taken, learner chose "build now, study later")

| # | Decision |
|---|----------|
| D1 | Migration `0005`: `requests` (one row per question), `request_sources` (the chunks it used, with score and rank), `audit_events` (one row per decision). RLS on all three, same tenant policy as Phase 4. `rag_app` may INSERT/SELECT; it may UPDATE only `requests` (to finalise them); it can never UPDATE or DELETE audit events. |
| D2 | **Append-only**: a trigger raises on any UPDATE or DELETE of `audit_events`, for every role (Invariant 6). Only someone who can disable triggers (a superuser) could change a row, and that is exactly what `/verify` detects. |
| D3 | **Hash chain per tenant**: each event stores `seq` (1, 2, 3… within the tenant), `prev_hash`, and `row_hash = SHA-256(prev_hash + canonical JSON of the row's content)`. The first row's `prev_hash` is 64 zeros. A per-tenant advisory lock serialises appends, so two requests can't fork the chain. Hashing is done in Python (`app/audit/chain.py`, pure and unit-tested) and recomputed by `verify`. |
| D4 | **No raw text at rest** (Invariant 5): `requests` stores `query_hmac` (HMAC-SHA-256 with `AUDIT_HMAC_KEY`, so the same question can be found again without storing it), `query_redacted` and `answer_redacted` (secrets and sensitive personal data masked, as in Phase 5). Event `details` hold ids, counts, scores, and reasons, also passed through the redactor. |
| D5 | **What is recorded**: request start (`status=started`) → `input_guard`, `retrieve` (candidates, top-k ids), `context_guard` (each DROP/MASK), `output`, `citations`, `grounding` verdicts, then `finish` with the final status and per-step timings. A guard outage records `error` and the reason type. ACL changes and refused ACL attempts are audited (`acl_change`). Auditor reads are themselves audited (`audit_read`). **Amended 2026-11-03 (tester v0.6.0):** a failure also records the decisions made before it, its sources, the failed step and the timings (T-2); refused (403) and not-found (404) audit reads are `audit_read` BLOCK (T-4); a guard that changed nothing records PASS with a reason (T-5). |
| D6 | **Fail closed**: if the request row or its events can't be written, the request is refused (503). An answer that can't be explained isn't given. |
| D7 | **Auditor API** (`auditor` permission, else 403; tenant-scoped by RLS): `GET /v1/audit/requests/{request_id}` (request + sources + events), `GET /v1/audit/requests?status=&user_id=&since=&limit=`, `GET /v1/audit/verify` → `{ok, rows_checked, first_broken}`. Seeded user `audrey@aldermoor.example.com` (employee, `auditor`). |
| D8 | **Observability**: the graph records per-node durations (`AnswerResult.timings`, ms); they go into the `finish` event and `requests.latency_ms`, and one structured JSON log line per request (request id, user id, status, timings, no question text). This separates our time from the model providers' time (ISS-029). |
| D9 | **Deferred**: self-hosted Langfuse (ISS-054). Its current self-hosted setup needs about six services (ClickHouse, Redis, object storage, workers); the concepts (spans, timings, redaction) are delivered here first. |

## Slices

| Slice | Issue | What |
|-------|-------|------|
| S1 | ISS-050 | Migration `0005`, append-only trigger, hash chain (`append`, `verify`), tamper tests |
| S2 | ISS-051 | Record every `/v1/ask` and ACL change: request row, sources, events, HMAC, redaction, timings; fail closed |
| S3 | ISS-052 | Auditor endpoints (`/v1/audit/requests…`, `/verify`), auditor user, audited reads |
| S4 | ISS-053 | Structured logs, lesson, tester run, release `v0.6.0` |

## Scope limits

- No Langfuse (ISS-054), no WORM/off-site copy of the chain (production plan), no retention or deletion jobs.
- No audit of ingest (a command, not a request) beyond what ingest already prints; logged for later if needed.

## Check when done

- Any `/v1/ask` request can be opened by an auditor and shows its sources and every decision in order.
- `UPDATE`/`DELETE` on `audit_events` is refused; after a superuser edits or deletes a row, `/verify` names the first broken `seq`.
- No raw question, raw answer, or unmasked personal data in `requests` or `audit_events` (tested with a question containing an IBAN).
- An auditor of Aldermoor sees no Northgate requests; a non-auditor gets 403.
- Quality and leakage unchanged; the tester's report is in `docs/test-reports/`.
