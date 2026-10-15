# 02 — Postgres, API, and a baseline eval

## Goal

Move from a script with an in-memory index to a real service: chunks and embeddings stored in Postgres + pgvector, a FastAPI `POST /v1/ask`, and a minimal evaluation harness that produces the **baseline score** every later phase must beat.

## Decisions (agreed 2026-10-15 — "all recommended")

| # | Decision |
|---|----------|
| D0 | Embeddings: **Mistral `mistral-embed`**, 1024-d ([ADR-0005](../../docs/adr/0005-mistral-embeddings.md)). OpenAI not required. |
| D1 | Database access: **plain SQL** with `psycopg` + `pgvector`; **Alembic** only versions raw-SQL migrations in `db/migrations/`. No ORM. |
| D2 | Tables: `tenants`, `users`, `documents`, `chunks`, with `tenant_id` and `allowed_roles` from day one; one seeded tenant (Aldermoor) and role (`employee`). `documents.slug` (= doc id) unique per tenant + UUID primary keys; chunks keyed by `(document, page, index)`. RLS stays off until Phase 4; `content_tsv` waits for Phase 3. |
| D3 | A **non-superuser `rag_app`** role for the application from the start (superusers bypass RLS); migrations run as the admin. A test asserts `rag_app` is not a superuser. |
| D4 | One `search(question, k)` interface, **two implementations**: in-memory (unit tests) and Postgres (app). Postgres uses cosine distance with an HNSW index; score = 1 − distance. The `Answerer` doesn't change. |
| D5 | Ingest command `python -m app.ingest`: one transaction per document; unchanged content hash → skipped; changed → chunks replaced in the same transaction; file removed → document removed. |
| D6 | Database tests use **testcontainers** (throwaway Postgres per run), marked `db`; fast tests run alone with `pytest -m "not db"`. |
| D7 | API: `POST /v1/ask` `{question}` (1–1,000 chars) → `{answer, citations: [{doc_id, page, source}], request_id, status}`; `422` bad input, `503` model/embedding failure (no stack traces); **no auth until Phase 4, so bind to `127.0.0.1` only**; `GET /healthz` checks the DB. |
| D8 | Golden set grows to **20** (+7 answerable incl. 2 two-document, +3 unanswerable incl. 2 near-misses), using the newer documents; checked by script. |
| D9 | Answer correctness = **key facts** per question (share found); unanswerable correct only if No-Answer. Also report recall@5, MRR, No-Answer accuracy, p50/p95 latency. |
| D10 | Eval runs through the real API in-process (FastAPI test client): `python -m eval.run`. Reports to `eval/reports/` (not committed); **baseline committed** to `eval/baselines/phase2.json`. |
| D11 | **The learner writes** the Postgres search query (step 6) and the eval metrics (step 9) against provided tests; the agent writes plumbing and explains it. |

## Steps (detailed after Lesson 2)

1. Switch to Mistral; first real run; close Phase 1 (needs ISS-015 fixed).
2. Lesson 2 — vector databases, SQL, Docker, APIs, measuring quality.
3. Finish this spec (implementation, scope limits, checks); slice into issues.
4. Docker Compose + Postgres + pgvector + migrations + `rag_app`.
5. Ingest command.
6. **Postgres search (learner).**
7. FastAPI `/v1/ask`, `/healthz`.
8. Golden set to 20.
9. **Eval metrics (learner).**
10. Baseline run, committed.
11. Walkthrough + quiz + experiment.
