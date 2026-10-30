# Lesson 2 — From a script to a service: databases, APIs, and measuring quality

> Phase 2 is learned **while building**: each slice adds its section here when it is built.
> Spec: `context/feature-specs/02-postgres-api-baseline.md`. Glossary terms in **bold** are defined in `GLOSSARY.md`.

| Slice | Section | Status |
|-------|---------|--------|
| S1 | Databases, Docker, migrations, least privilege | ✅ 2026-10-22 |
| S2 | Ingest: transactions, hashing, idempotency | ✅ 2026-10-22 |
| S3 | Vector search in SQL | ✅ 2026-10-29 |
| S4 | APIs and HTTP | ✅ 2026-10-29 |
| S5 | What makes a good test question | ✅ 2026-10-29 |
| S6 | Metrics: recall@5, MRR, key facts | ✅ 2026-10-29 |
| S7 | Baselines | ✅ 2026-10-30 |

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

### "Why not a vector database?" (asked 2026-10-22)

We **are** using one: pgvector makes Postgres a vector database. What we skipped is a *dedicated* one (Pinecone, Qdrant,
Weaviate, Chroma). Decision: ADR-0001.

| | Dedicated vector DB | Postgres + pgvector (ours) |
|---|---|---|
| Vector search | excellent | good (same HNSW algorithm) |
| Hundreds of millions of vectors, very high traffic | wins | possible, needs tuning |
| Documents, users, tenants, audit in the same place | no: a second database | yes |
| One transaction across vectors and other data (S2) | no | yes |
| Company isolation enforced by the database (row-level security, Phase 4) | filters you must remember | yes |
| Systems to run and back up | 2+ | 1 |

For a **secure** RAG system, the hard problem is *who may see what*, not raw speed, and at our scale (23 chunks; a small
company might have about 100k) pgvector is fast enough. Cost of the choice: a very selective filter can make HNSW return
fewer than k rows, which pgvector ≥ 0.8 fixes with iterative scan (hence the pinned 0.8.7).

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

---

## S3 — Vector search in SQL ✍️ (ISS-022)

### SQL in six words

```sql
SELECT   <columns>                      -- what to give back
FROM     <table>                        -- where to look
JOIN     <other table> ON <link>        -- bring in a related table
WHERE    <conditions joined by AND>     -- which rows count
ORDER BY <expression>                   -- in what order (ASC = smallest first, the default)
LIMIT    <n>                            -- how many
```

Real examples on our database (2026-10-22):

| Query | Result |
|-------|--------|
| `SELECT slug, source FROM documents ORDER BY slug LIMIT 3;` | `annual-leave-policy`, `employee-handbook`, `expense-policy` |
| `… FROM chunks c JOIN documents d ON d.id = c.document_id WHERE d.slug LIKE 'vendor%'` | each chunk *with its document's slug*: the JOIN links a chunk to its document |
| `SELECT ARRAY['employee'] && ARRAY['employee','hr']` | `t`: `&&` means "share at least one element" |

### Distance vs similarity

pgvector's `<=>` gives the **cosine distance** between two vectors: **0 = same direction (same meaning)**, larger = less related.
Our app's `score` is **cosine similarity**: **1 = same meaning**. They're two views of one number:

> **similarity = 1 − distance**

Real result: the leave policy's first chunk compared with every chunk:

| Chunk | Distance | Similarity |
|-------|---------:|-----------:|
| annual-leave-policy, chunk 0 (itself) | 0.000 | 1.000 |
| annual-leave-policy, chunk 1 | 0.067 | 0.933 |
| sickness-absence-policy, chunk 0 | 0.088 | 0.912 |
| remote-work-policy, chunk 0 | 0.093 | 0.907 |

### Why "order by the distance itself"

The HNSW index (S1) is a map organised by **distance**. Postgres can walk it to find "closest first", but only when the
query says `ORDER BY embedding <=> <question>` (ascending). If you order by something *computed from* the distance (like
`score DESC`), Postgres can't use the map: it computes every row's score and sorts them all. That's the same answer,
but slow on a million chunks.

### Parameters, not pasted values

Values arrive as `%(name)s` placeholders, and psycopg sends them separately from the SQL text. Never build SQL by pasting
values into the string: that is how **SQL injection** happens (S1).

### The exercise

File: `app/retrieval/pg_search.py`, the `_SEARCH_SQL` string. Tests: `uv run pytest -m db tests/test_pg_search.py -v` (14 tests).
Fill in the five blanks:

```sql
SELECT d.slug, d.source, c.page, c.chunk_index, c.content,
       ①_____ AS score
FROM chunks c
JOIN documents d ON ②_____
WHERE ③_____
ORDER BY ④_____
LIMIT ⑤_____
```

| Blank | Hint | Test that checks it |
|-------|------|---------------------|
| ① | similarity from distance; the question's vector is `%(embedding)s` | `test_score_is_cosine_similarity_not_distance` |
| ② | which column of a chunk points to its document? (see the JOIN example above) | `test_chunk_has_its_id_…` |
| ③ | three conditions: same tenant, active, shares a role (`&&`) | the three "never returned" tests |
| ④ | closest first, using the distance itself | `test_the_query_can_use_the_hnsw_index` |
| ⑤ | a placeholder | `test_returns_at_most_k_chunks` |

Columns you can use: `chunks c`: `document_id, tenant_id, allowed_roles, page, chunk_index, content, embedding, is_active`;
`documents d`: `id, slug, source`.

### S3 result (2026-10-29)

At the learner's request (2026-10-29, "Option A"), the assistant wrote the query; the learner explains it back.
14/14 search tests pass. Then the app was connected: the CLI now searches Postgres whenever `DATABASE_URL` is set.

Same real question, before and after:

| | In memory (before) | Postgres (after) |
|---|---|---|
| Top 5 scores | 0.850, 0.842, 0.785, 0.759, 0.747 | **the same** |
| Texts sent to Mistral per question | 24 (23 chunks + the question) | **1** (the question) |
| Time (incl. the Groq answer) | 5.1 s | 3.2 s |
| "What is the CEO's salary?" | No-Answer, best 0.692 | No-Answer, best 0.692 |

Identical scores show the two searches agree (the `test_same_results_as_the_in_memory_search` test, proven on real data).

### Explain it back (your turn)

1. In your own words, what does each of the five parts do: JOIN, WHERE, ORDER BY, LIMIT, `1 - (… <=> …)`?
2. Which line is the *security* part, and what would leak if it were deleted?
3. Why did the database version send 1 text to Mistral instead of 24?

---

## S4 — The web API (ISS-023)

Built at pace (the learner chose "build now, study later"), so study this section afterwards.

### The ideas

- **API** (Application Programming Interface): a door that lets *other programs* use ours: a website, a phone app, a Slack bot.
- **HTTP**: the language of that door. A program sends a **request** (a *method* such as `GET` or `POST`, a *path* such as
  `/v1/ask`, and a *body* in **JSON**) and gets a **response**: a **status code** plus a JSON body.
- **Status codes** say what happened, so the caller knows what to do next:

| Code | Means | When we send it |
|------|-------|-----------------|
| 200 | OK | answered, **or** "I don't know" (a correct outcome, not an error) |
| 422 | your input is invalid | missing, empty, only spaces, over 1,000 characters, not text |
| 503 | temporarily unavailable, try again | model, embedding, or database failure |

- **Validation at the door**: the `AskRequest` model rejects bad input *before* any AI call, which costs nothing and gives a clear error.
- **Never leak internals**: a 503 says only "temporarily unavailable". Real error text can contain keys or internal paths
  (a test uses `api_key=sk-secret-123` inside an error to prove it never reaches the caller).
- **Logs without secrets** (Invariant 5): the server logs the *type* of failure and a `request_id`, never the question.
  Real check: 0 question words in the server log.
- **request_id**: a unique id per request, so a user can report "request 8893…" and we can find it (the audit trail uses it from Phase 6).
- **127.0.0.1 only**: no login until Phase 4, so the API listens only on this Mac. Real check: `listening on 127.0.0.1:8000`.
- **Build once at start-up**: the answerer (database pool + models) is created when the server starts, not per request.

### Real runs (2026-10-29)

```
GET  /healthz                               → 200 {"status":"ok"}
POST /v1/ask "How many days of annual leave…" → 200, answer + citation annual-leave-policy:1 (2.7 s)
POST /v1/ask "What is the CEO salary?"      → 200, status "no_answer"
POST /v1/ask "   "                          → 422
database stopped: /healthz                  → 503 {"status":"unavailable"}
database stopped: /v1/ask                   → 503 {"detail":"The assistant is temporarily unavailable. Try again."}
```

### A real bug found by breaking things on purpose (ISS-027)

After a database **restart**, `/healthz` said OK (it opens a fresh connection each time), but `/v1/ask` failed **forever**: it
held the one connection opened at start-up, and the restart had killed it. In production, that's an outage that looks healthy.

Fix: a **connection pool** (`app/db.py` → `make_pool`). A few connections are kept ready, and each is **checked before use**
and replaced if dead; concurrent requests also stop sharing one connection. A regression test kills the app's connections
and asks again. Real result after the fix: restart the database → the next request returns 200.

Lessons: test failure, not just success (stop the database and see what happens); and a health check that tests something
*different* from the real path can say "OK" while users get errors.

### How to start it (checklist)

1. **Docker Desktop is open** (whale icon in the menu bar, not animating).
2. **You're in the project folder**: `cd ~/Desktop/shashank/generative-ai/secure-rag-assistant`
3. **The database is up**: `docker compose up -d`, then `docker compose ps` shows `(healthy)`.
4. **Start the server**: `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`
5. When it prints `Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)`, **it's running**. The terminal stays
   busy on purpose: the server waits for requests. Leave it open, and use a browser or a second terminal.
6. Stop it with **Ctrl+C** in that terminal.

| You see | Meaning | Fix |
|---------|---------|-----|
| `Cannot reach the database at 127.0.0.1:5433. Is Docker running?` | the database isn't up | steps 1 and 3 |
| `Failed to spawn: uvicorn` | wrong folder | step 2 |
| `address already in use` | a server is already running on 8000 | use it, or stop it (Ctrl+C in its terminal) |
| the terminal "just sits there" | it's working (step 5) | open http://127.0.0.1:8000/docs |

### Try it yourself

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
# in another terminal:
curl 127.0.0.1:8000/healthz
curl -X POST 127.0.0.1:8000/v1/ask -H 'Content-Type: application/json' -d '{"question": "How much leave do I get?"}'
# or open http://127.0.0.1:8000/docs in a browser: FastAPI's interactive page
```

### Explain it back (later)

1. Why is "I don't know" a 200 and not an error code?
2. Why doesn't the 503 response include the real error message?
3. Why did `/healthz` say OK while `/v1/ask` was failing, and how does the pool fix it?

---

## S5 — A better test set (ISS-024)

The **golden set** (`eval/datasets/golden.jsonl`) grew from 10 to **20** questions: **14 answerable** (4 need two documents)
and **6 unanswerable**. In S6/S7 we score the system on it, so the score is only as good as these questions.

### What makes a good test question

| Kind | Example | What it tests |
|------|---------|---------------|
| Simple fact | g12 "speed limit in our depot yards?" → 5 mph | search + reading |
| Personal situation | g11 "I've worked here 3 years: how much sick pay?" → 6 weeks | applying a rule (1–5 years row) |
| Two documents | g17 gift → rule in the handbook, person in the org chart | combining sources |
| Comparison | g16 "pay SwiftParts or TrackLine sooner?" → TrackLine, 30 vs 45 days | reasoning over two facts |
| **Near-miss** | g18 "motorway speed limit?" (only the 5 mph *yard* limit exists) | not inventing from general knowledge |
| **Near-miss** | g19 "Leeds depot address?" (only Felixstowe's is given) | not stretching a similar fact |
| Out of scope | g20 "employee of the year 2025?" | saying "I don't know" |

### Key facts

Each answerable question lists **key facts**: short phrases a correct answer must contain (g13: `24 hours`, `SafeSite`).
Code can then check answers automatically, without a person reading every one; S6's score is the share of key facts found.

### Testing the tests

`uv run python -m scripts.check_golden` proves every key fact is really on one of its expected pages, every source page
exists, ids are unique, unanswerable entries expect exactly the No-Answer sentence, and the counts are 14 / 6.
A typo in a test ("26 days") would otherwise make a correct answer look wrong; a test catches that too.

### Preview on the real system (2026-10-29)

New questions g11–g20: **9/10 behave correctly**. g17 fails the same way as g06: the org chart isn't in the top 5, so
"I don't know" is the honest reply. It's kept as a second test case for better search (ISS-017, Phase 3).

Also seen: the model writes `5 mph` (an invisible *narrow* space), `555‑0150` (a non-breaking hyphen), and `**bold**`.
S6's key-fact matching must treat these as the plain text.

---

## S6 — Measuring quality (ISS-025)

`eval/metrics.py`: pure functions (no AI, no database), each checked against hand-worked examples in `tests/test_metrics.py`.
Written by the assistant (build now, study later); the learner explains them back later.

### Retrieval: did search bring the right page?

**recall@5** = share of the expected pages that appear in the top 5.
- expected `[leave:1]`, top 5 has it → **1.0**
- expected `[leave:1, org:1]`, only leave found → **0.5** (two chunks of one page still count once)
- right page is 6th → **0.0**: the model never sees it.

**Reciprocal rank** = 1 / position of the first right page; **MRR** = its average over the questions.

| Right page at position | 1 | 2 | 4 | not found |
|------------------------|---|---|---|-----------|
| reciprocal rank | 1.0 | 0.5 | 0.25 | 0 |

Recall asks *"is it there at all?"*; MRR asks *"is it near the top?"*. Both matter: Phase 3 will change the order (reranking).

### Answers: is the answer right?

**Key-fact score** = share of the key facts found in the answer. Before comparing, both texts are **normalised**:
lowercase, `**bold**` removed, narrow and non-breaking spaces become plain spaces, special hyphens (`‑`) become `-`,
and whitespace is collapsed. Without this, the real answer `**5 mph**` wouldn't match the key fact `5 mph`.
A refused answerable question scores 0.

Known limit: it's a substring check. `£4200` won't match `£4,200`, and a fact written in other words won't match.
Phase 7 adds an AI judge for meaning.

### Refusing: "I don't know" exactly when it should

| Question | System said | Verdict |
|----------|-------------|---------|
| unanswerable | I don't know | ✅ correct |
| unanswerable | an answer | ❌ invented |
| answerable | an answer | ✅ |
| answerable | I don't know | ❌ **false refusal** |

**No-Answer accuracy** = share of unanswerable questions refused. **False refusals** = answerable questions refused.
A system that always says "I don't know" scores 100% No-Answer accuracy and is useless, so we report both.

### Speed: latency percentiles

**p50** (median) = half the answers were faster. **p95** = 95% were faster: the "slow but normal" case users notice.
Averages hide slow outliers; percentiles show them. Example: `[1, 2, 3, 4, 10]` s → p50 = 3 s, p95 = 8.8 s.

### The summary

`summarise(results)` gives: questions, recall@5, MRR, key-fact score, answered rate, false refusals, No-Answer accuracy,
p50/p95 latency. S7 runs the 20 golden questions through the real API and saves these numbers as the **baseline**.

### Explain it back (later)

1. Search finds the right page in 5th place. What are recall@5 and the reciprocal rank?
2. Why report false refusals alongside No-Answer accuracy?
3. Why p95 and not just the average?

---

## S7 — The baseline (ISS-026)

`uv run python -m eval.run --save-baseline` sends the 20 golden questions through the **real API** (in-process), with the
real models and the database, scores them with S6's metrics, and saves the report as `eval/baselines/phase2.json`.

**Baseline** = the scores of a fixed, committed version. Every later change is compared against it: a new idea is kept only
if the numbers say it helped. Without one, "it seems better" is a guess.

### Phase 2 baseline (2026-10-30)

| Metric | Value | Reading |
|--------|------:|---------|
| recall@5 | 0.929 | the right page was in the top 5 for 13 of 14 answerable questions (g06 and g17 found only one of their two pages) |
| MRR | 0.917 | when found, the right page was almost always first |
| key-fact score | 0.857 | 12 answers had every key fact; the 2 refusals scored 0 |
| answered | 12 / 14 | 2 **false refusals**: g06 and g17 both need the org chart, which search doesn't find (ISS-017) |
| No-Answer accuracy | 6 / 6 | every trick and near-miss question got "I don't know" |
| latency p50 / p95 | 9.5 s / 13.3 s | **misleading**: g01–g06 took ~1.4 s, then Groq's free tier slowed the burst to ~10 s (ISS-029) |

### What it tells us to do next

- The two failures are **retrieval** failures, not answer failures: recall@5 and the refusals point at the same cause.
  Phase 3 (keyword + vector search, reranking) targets exactly this; success = g06 and g17 answered without losing the others.
- Numbers come with context: the latency here measures the free tier's throttling as much as our system.
  A baseline records its settings (models, prompt version, chunk size, top k, git commit) so a later run is a fair comparison.

### Explain it back (later)

1. Why are g06 and g17 "retrieval" failures, and which two numbers show it?
2. Why must a report record the model, prompt version, and chunk settings?
3. Why shouldn't Phase 7 trust this latency number?
