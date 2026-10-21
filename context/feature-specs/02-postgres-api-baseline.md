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

## Implementation

1. **Database in Docker** — `docker-compose.yml` runs `pgvector/pgvector:pg16`, bound to `127.0.0.1:5433` (5432 is taken by a local Postgres on the dev machine). Admin password and the `rag_app` password come from `.env`; `.env.example` lists the keys (`POSTGRES_PASSWORD`, `DATABASE_ADMIN_URL`, `DATABASE_URL`).
2. **Migrations** — Alembic in `db/`, raw SQL only (`op.execute`), run as the admin via `DATABASE_ADMIN_URL`:
   - `vector` extension; `tenants (id uuid PK, name text unique, roles text[])`; `users (id uuid PK, tenant_id FK, email text, roles text[])`.
   - `documents (id uuid PK, tenant_id FK, slug text, source text, content_hash text, allowed_roles text[], version int, status text, ingested_at timestamptz, UNIQUE (tenant_id, slug))`.
   - `chunks (id uuid PK, document_id FK ON DELETE CASCADE, tenant_id uuid, allowed_roles text[], page int, chunk_index int, content text, embedding vector(1024), embedding_model text, content_hash text, is_active bool, UNIQUE (document_id, page, chunk_index))`.
   - Indexes: HNSW on `embedding` (`vector_cosine_ops`); B-tree on `(tenant_id, is_active)`.
   - Seed: tenant **Aldermoor** with roles `{employee}`.
   - Role `rag_app` (LOGIN, NOSUPERUSER, NOBYPASSRLS) with `SELECT, INSERT, UPDATE, DELETE` on the four tables; its password is read from `DATABASE_URL` at migration time, never written in a committed file.
3. **Ingest** — `python -m app.ingest` (as `rag_app`): for each file in `corpus_dir`, compute the content hash; unchanged → skip; new or changed → in **one transaction** upsert the document, delete its chunks, insert the new chunks with embeddings and `embedding_model`; documents whose file is gone → deleted (chunks cascade). Prints `added / updated / unchanged / removed` counts. Reuses `load_pages`, `chunk_pages`, `make_embeddings`.
4. **Retriever** — a `Retriever` protocol, `search(question, k) -> list[ScoredChunk]`. `ChunkIndex` (in-memory) already fits. **`PgRetriever` (learner writes the query):** embed the question, then one SQL query ordered by cosine distance (`<=>`), filtered by `tenant_id`, `is_active`, and `allowed_roles && roles`; `score = 1 - distance`; returns domain `Chunk`s with ids `slug:page:index`. `Answerer` accepts any `Retriever`; nothing else in answering changes.
5. **API** — `app/main.py` (FastAPI). The answerer is built once at start-up with `PgRetriever`.
   - `POST /v1/ask` `{question}` (1–1,000 chars) → `{answer, citations: [{doc_id, page, source}], request_id, status}`.
   - `422` on invalid input; `503 {"detail": "…temporarily unavailable"}` on a model, embedding, or database failure, with no stack trace in the body.
   - `GET /healthz` → `{"status": "ok"}` after `SELECT 1`, `503` if the database is down.
   - Run with `uvicorn app.main:app --host 127.0.0.1` only (no auth until Phase 4).
6. **Golden set → 20** — +7 answerable (2 need two documents, using the newer documents), +3 unanswerable (2 near-misses). Every entry gains `key_facts: list[str]`. `scripts/check_golden.py` checks: unique ids, counts (14 / 6), every expected source exists as a `doc_id:page`, and every key fact appears on one of its expected pages.
7. **Eval metrics (learner writes)** — `eval/metrics.py`, pure functions: `recall_at_k`, `reciprocal_rank`, `key_fact_score` (normalises real model output: case, `**bold**`, narrow no-break spaces, non-breaking hyphens), `no_answer_correct`, and `percentile` for latency.
8. **Eval runner** — `python -m eval.run`: through the FastAPI test client (real models, real Postgres) for answers and latency; retrieval metrics from the app's `Retriever` directly (the API doesn't expose chunks). Report → `eval/reports/<timestamp>.json` (gitignored); `--save-baseline` writes `eval/baselines/phase2.json` (committed). Report fields: model names, `prompt_version`, chunk settings, `top_k`, per-question rows, and the summary metrics.

## Layout (new in Phase 2)

```
docker-compose.yml
db/alembic.ini, db/env.py, db/migrations/   raw-SQL migrations
app/db.py                    connection helpers (rag_app via DATABASE_URL)
app/ingest.py                python -m app.ingest
app/retrieval/retriever.py   Retriever protocol
app/retrieval/pg_search.py   PgRetriever            ← learner
app/main.py                  FastAPI app: /v1/ask, /healthz
eval/metrics.py              metric functions        ← learner
eval/run.py                  python -m eval.run
eval/baselines/phase2.json   committed baseline
scripts/check_golden.py
tests/conftest.py            Postgres testcontainer fixture (marker `db`)
```

## Slices (build order)

Each slice ends green, committed, and pushed, and opens with a short concept lesson (added to `lessons/02-…md`).

| Slice | Issue | What | Concept first | Who codes | Needs Docker | Blocked by |
|-------|-------|------|---------------|-----------|--------------|------------|
| S1 | ISS-020 | Postgres in Docker, migrations, seed, `rag_app`, DB test fixture | Docker, tables, migrations, roles | agent | yes | — |
| S2 | ISS-021 | Ingest command | transactions, hashing, idempotency | agent | yes | S1 |
| S3 | ISS-022 | `Retriever` + **`PgRetriever` query**; CLI on Postgres | vector search in SQL, `<=>`, HNSW | **learner** | yes | S2 |
| S4 | ISS-023 | FastAPI `/v1/ask`, `/healthz` | HTTP, APIs, status codes, validation | agent | tests no; run yes | S3 |
| S5 | ISS-024 | Golden set to 20 + key facts + checker | what makes a good eval question | agent; learner reviews | no | — |
| S6 | ISS-025 | **Eval metrics** | recall@5, MRR, key facts, percentiles | **learner** | no | S5 |
| S7 | ISS-026 | Eval runner, baseline committed, release `v0.2.0` | baselines, comparing runs | together | yes | S4, S6 |

S5 and S6 don't need Docker, so they can be done whenever Docker isn't running.

## Scope limits

- No auth, no users in requests, no RLS (Phase 4). Invariant 1 is met only by the query filter until Phase 4; this is acceptable while there's one tenant and the API listens on `127.0.0.1` only.
- No hybrid search, no `content_tsv`, no reranker, no LangGraph (Phase 3).
- No upload endpoint or ingestion jobs table (Phase 4); ingestion is a command.
- No guards, no audit tables (Phases 5–6). No `requests` table yet.
- No prompt change (`answer_v1` stays), so the baseline measures the Phase 1 behaviour on the new storage.
- No CI gate (Phase 7); the baseline is recorded, not enforced.

## Check when done

- `docker compose up -d` and `alembic upgrade head` give the four tables, the HNSW index, and the seeded tenant; a test asserts `rag_app` is not a superuser and cannot bypass RLS.
- `python -m app.ingest` stores 11 documents / 23 chunks; a second run reports 11 unchanged; editing one file updates only that document; a failure mid-document leaves the old chunks intact.
- `PgRetriever` passes the same retrieval tests as `ChunkIndex` (best first, k respected, scores in [-1, 1]) plus: only active chunks, only the tenant's chunks.
- `curl -X POST 127.0.0.1:8000/v1/ask -d '{"question": "…"}'` returns an answer with citations; bad input → 422; model failure → 503 with no stack trace; `/healthz` → 200, or 503 with the DB stopped.
- `scripts/check_golden.py` passes on 20 entries.
- `python -m eval.run --save-baseline` writes `eval/baselines/phase2.json` with recall@5, MRR, key-fact correctness, No-Answer accuracy, p50/p95 latency; numbers recorded in `CHANGELOG.md`.
- `uv run pytest` (no Docker, no network) passes; `uv run pytest -m db` passes with Docker; `uv run pytest -m live` passes with keys.
- The learner can explain the `PgRetriever` query and each metric they wrote.
