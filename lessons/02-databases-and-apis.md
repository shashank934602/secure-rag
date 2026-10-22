# Lesson 2 — From a script to a service: databases, APIs, and measuring quality

> Phase 2 is learned **while building**: each slice adds its section here when it is built.
> Spec: `context/feature-specs/02-postgres-api-baseline.md`. Glossary terms in **bold** are defined in `GLOSSARY.md`.

| Slice | Section | Status |
|-------|---------|--------|
| S1 | Databases, Docker, migrations, least privilege | ✅ 2026-10-22 |
| S2 | Ingest: transactions, hashing, idempotency | ✅ 2026-10-22 |
| S3 | Vector search in SQL | — |
| S4 | APIs and HTTP | — |
| S5 | What makes a good test question | — |
| S6 | Metrics: recall@5, MRR, key facts | — |
| S7 | Baselines | — |

---

## S1 — The database (ISS-020)

### Why a database at all?

In Phase 1, **every question** re-read 11 files, re-cut 23 chunks, and paid Mistral to re-embed all of them. Everything
lived in memory and vanished when the program stopped. A database keeps the chunks *and their 1,024 numbers* on disk:
**embed once, search many times.**

### Postgres and pgvector

- **Postgres** stores data in **tables**: like spreadsheets, but every column has a fixed type and rules.
- **pgvector** (version 0.8.7 in our container) adds a column type `vector(1024)` and fast "find the closest vectors" search.

Our four tables, and why each exists:

| Table | One row is… | Why now (Phase 2) |
|-------|-------------|-------------------|
| `tenants` | a company (seeded: **Aldermoor**, roles `{employee}`) | every row is labelled with its company from day one, so Phase 4 security needs no rewrite |
| `users` | a person in a company | empty until Phase 4 (login) |
| `documents` | one file: `slug` (the doc id), `source`, `content_hash`, `allowed_roles` | `UNIQUE (tenant_id, slug)`: no two documents share a doc id within a company |
| `chunks` | one chunk: text, `page`, `chunk_index`, **`embedding vector(1024)`** | the thing we search |

The table **enforces rules itself**, so a bug in our Python can't break them. Each rule is proven by a test:

| Rule in the table | What it prevents | Test |
|-------------------|------------------|------|
| `embedding vector(1024)` | storing a 1,536-number OpenAI vector by mistake | `test_a_wrong_size_embedding_is_rejected` |
| `UNIQUE (tenant_id, slug)` | two documents with the same doc id | `test_a_slug_is_unique_within_a_tenant` |
| `ON DELETE CASCADE` | orphan chunks of a deleted document still being searched | `test_deleting_a_document_deletes_its_chunks` |
| `CHECK (page >= 1)` | page 0 (pages are 1-based, spec 01 D3) | — |

**Indexes.** Without an index, search compares the question with *every* chunk: fine for 23, slow for a million.
**HNSW** builds a "map of neighbours" so search jumps to the right area. It's *approximate*: very fast, and occasionally
misses a true neighbour. A second index on `(tenant_id, is_active)` speeds up "only this company's live chunks".

### Docker

Docker runs a program inside a **container**, a sealed box with everything it needs, separate from your Mac.

- **Image** = the recipe: `pgvector/pgvector:pg16` (Postgres 16 with pgvector built in).
- **Container** = a running box made from the image.
- **Volume** `pgdata` = the box's hard drive, kept when the container stops.
- **Port** `127.0.0.1:5433 → 5432`: the box listens on 5432 *inside*; your Mac reaches it on door **5433** (5432 was
  already taken by a local Postgres), and only from this machine (`127.0.0.1`).

```
docker compose up -d      start          docker compose ps      is it healthy?
docker compose down       stop (keeps data)   docker compose down -v   stop and delete data
```

### Migrations

A **migration** is a numbered SQL script that changes the database's shape (`db/migrations/0001_initial_schema.py`).
Alembic records which ones have run in a table called `alembic_version`, so every machine reaches the *same* schema by
running them in order: `uv run alembic -c db/alembic.ini upgrade head`. Real output: `0001 (head)`.

Rules: never edit a migration once it has run; add a new one (Phase 3 will add `0002`).

### Least privilege: admin vs `rag_app`

| | `postgres` (admin) | `rag_app` (the app) |
|---|---|---|
| Used for | running migrations only | everything the app does |
| Superuser? | yes (`rolsuper = t`) | **no** (`f`) |
| Bypasses row-level security? | yes | **no** (`f`) |
| Can read/write rows | yes | yes |
| Can create or drop tables | yes | **no**: real result `drop table chunks` → `InsufficientPrivilege` |

Why it matters: if the app is ever tricked (a bug, an injection), it can only do what `rag_app` can do. And from Phase 4,
**row-level security** keeps companies apart, but superusers skip it, so the app must never be one.

The `rag_app` password is never written in a committed file: the migration reads it from `DATABASE_URL` and Postgres quotes
it safely (`%L`), instead of pasting it into SQL text. Pasting is how **SQL injection** happens.

### Tests against a throwaway database

`uv run pytest -m db` starts a fresh Postgres in Docker (**testcontainers**), runs every migration, runs 11 tests, then
deletes it. Tests never touch your real data, and every run starts from the same clean state.

### Check questions

1. Why does `chunks` store `tenant_id` and `allowed_roles` again when `documents` already has them?
2. The app could connect as `postgres` and everything would "work". What would we lose?
3. Why is the vector column `vector(1024)` and not just "a list of numbers of any length"?

<details><summary>Answers</summary>

1. So search can filter on the chunk row alone, in the same query that finds the closest vectors (ADR-0002); no
   join to `documents` is needed for every result, and the security rule sits right next to the data it protects.
2. Least privilege: a bug or attack could drop tables or change the schema, and from Phase 4 the app would skip
   row-level security, so one company could see another's chunks.
3. Every embedding from `mistral-embed` has exactly 1,024 numbers; a fixed size lets the index work and makes the
   database reject a vector from the wrong model (e.g. 1,536 from OpenAI) instead of silently mixing them.
</details>

---

## S2 — Ingest: filling the database (ISS-021)

**Ingest** = load → chunk → embed → store, **once**, so questions only embed the question.
Command: `uv run python -m app.ingest`. Real runs on the 11 documents:

| Run | Result | Time | Mistral calls |
|-----|--------|-----:|---------------|
| 1st | `added 11 · updated 0 · unchanged 0 · removed 0` | 9.6 s | all 23 chunks embedded |
| 2nd | `added 0 · updated 0 · unchanged 11 · removed 0` | 0.7 s | **none** |

### Fingerprints (hashing)

A **content hash** (SHA-256) turns a file's bytes into a 64-character fingerprint, e.g. `c199c3e2617b…` for the leave
policy. Change a single letter and the fingerprint is completely different. We store it in `documents.content_hash`; on the
next run, **same fingerprint → skip** (no model call, no cost), different → re-process only that document.

### Transactions: all or nothing

Updating a document is three steps: update its row, delete its old chunks, insert the new ones. If the program died
between steps 2 and 3, the document would vanish from search. `with conn.transaction():` makes the database apply **all
three or none**: any error rolls everything back.

Proven by `test_a_failed_document_keeps_its_previous_version`: a fake model returns 3 numbers instead of 1,024, the
database rejects the new chunks half-way through, and the old fingerprint and chunks are still there. The other 10 documents
still go in, because each document has **its own** transaction (one bad file doesn't stop the rest).

Design choice: **embed before opening the transaction.** A transaction holds locks; a slow network call shouldn't.

### Idempotency: safe to run again

Running ingest twice gives the same result as once: no duplicates, no cost (proven: the 2nd run embedded **nothing**, and
the chunk rows are untouched). So you never need to remember whether you already ran it.

### What each situation does

| The file… | Ingest does | Report |
|-----------|-------------|--------|
| is new | insert document + chunks (version 1) | `added` |
| changed | in one transaction: update document (version + 1), replace its chunks | `updated` |
| is unchanged | nothing | `unchanged` |
| was deleted | delete the document; `ON DELETE CASCADE` removes its chunks | `removed` |
| fails | its transaction rolls back; the old version stays | `failed` (exit code 1) |

### Testing lesson

One test failed at first because **the test** guessed that the org chart has 1 chunk; it has 2. The fix was to *measure*
the count in the test instead of hard-coding a guess.

### Check questions

1. Why is embedding done *before* the transaction starts, not inside it?
2. If all 11 documents shared one transaction, what would happen when one of them fails?
3. You fix a typo in `expense-policy.md` and run ingest. Exactly which Mistral calls happen?

<details><summary>Answers</summary>

1. A transaction holds locks on the rows it changes; a slow or failing network call inside it would keep them locked
   (blocking searches) for no reason. Doing the slow work first keeps the transaction short.
2. Everything would roll back, so none of the 11 would be saved, even the 10 good ones. Per-document transactions isolate failures.
3. Only the expense policy's chunks (2) are embedded: its fingerprint changed; the other 10 match and are skipped.
</details>
