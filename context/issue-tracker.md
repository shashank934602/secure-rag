# Issue Tracker

Every bug, task, open question, and piece of tech debt gets an id here. Progress (what is built) lives in
`progress-tracker.md`; changes live in `CHANGELOG.md`.

## How to use

- **Id:** `ISS-NNN`, next free number, never reused.
- **Type:** `bug` · `task` · `question` · `debt`
- **Priority:** `P1` blocks the current phase · `P2` needed this phase · `P3` later / nice to have
- **Status:** `open` · `in-progress` · `blocked` (say on what) · `closed`
- To close: move the row to **Closed**, fill in the date and a one-line resolution. Never delete rows.
- Reference the id in commits, specs, and `CHANGELOG.md`.

## Open

| Id | Title | Type | Phase | Pri | Status | Opened | Notes |
|----|-------|------|-------|-----|--------|--------|-------|
| ISS-005 | Workflow skills missing: `/grill-with-docs`, `/to-spec`, `/to-tickets`, `/implement`, `/pr`, `/retro`, `/teach`, `/handoff` | question | 0 | P2 | open | 2026-10-12 | Plugin is installed but only `grilling`, `tdd`, `code-review`, `codebase-design`, `domain-modeling`, `research`, `prototype`, `diagnosing-bugs` are available. Update the plugin, or adapt `ai-workflow-rules.md`. |
| ISS-017 | g06 retrieval miss: the org chart isn't in the top 5 for "Who owns the SwiftParts contract… email?" | task | 3 | P2 | open | 2026-10-15 | Model correctly said "I don't know" — the right document never reached it. A retrieval problem for Phase 3 (hybrid search + reranking); keep g06 as the test case. |
| ISS-019 | Poisoned or conflicting documents: a plausible false document is answered faithfully | question | 4–5 | P2 | open | 2026-10-21 | Demo: a document saying "from 2026 all employees receive 40 days" won over the real 25-day policy. The answer cited `team-notice:1` and passed all checks; a grounding judge would also pass it (it *is* grounded), and an injection classifier looks for commands, not false facts. Candidate controls: uploader role (Phase 4), audit of who uploaded (Phase 6), document owner/authority metadata, conflict detection. Decide in Phase 4/5. |
| ISS-024 | Phase 2 S5: golden set to 20 + `key_facts` + `scripts/check_golden.py` | task | 2 | P1 | open | 2026-10-21 | Agent drafts, learner reviews. No Docker needed. |
| ISS-025 | Phase 2 S6: eval metrics in `eval/metrics.py` | task | 2 | P1 | open | 2026-10-21 | **Learner writes** recall@k, reciprocal rank, key-fact score, No-Answer check, percentile against provided tests. No Docker needed. Blocked by ISS-024. |
| ISS-026 | Phase 2 S7: eval runner, committed baseline, release `v0.2.0` | task | 2 | P1 | open | 2026-10-21 | Together. Blocked by ISS-023 and ISS-025. |
| ISS-016 | Production decisions D-P1 … D-P8 (users, hosting, hosting budget, domain, region, provider data policy, on-call, embedding-outage mode) | question | 8+ | P3 | open | 2026-10-13 | From `docs/production-plan.md` §3. Not needed until Phases 1–7 are done; hosting cost is outside the agreed < $20 AI budget. |

## Closed

| Id | Title | Type | Phase | Opened | Closed | Resolution |
|----|-------|------|-------|--------|--------|------------|
| ISS-001 | Embedding model: OpenAI `text-embedding-3-small` or local `bge-small-en-v1.5`? | question | 0 | 2026-10-10 | 2026-10-12 | `text-embedding-3-small`, 1536-d → `vector(1536)`. `bge-small` is the offline fallback. |
| ISS-002 | Reranker hardware: CPU only, or GPU? | question | 0 | 2026-10-10 | 2026-10-12 | CPU / Apple MPS on the M4; no GPU. |
| ISS-003 | Sample corpus: which documents? | question | 0 | 2026-10-10 | 2026-10-12 | Synthetic, LLM-generated, hand-edited; two tenants; fake PII; canary strings in tenant B. |
| ISS-004 | Should this folder be its own Git repo? | question | 0 | 2026-10-10 | 2026-10-12 | Yes — `shashank934602/secure-rag` (public), branch `main`. |
| ISS-008 | Remove remaining AI-tool mentions from tracked docs | task | 0 | 2026-10-12 | 2026-10-12 | Rewrote `plan.md` §4.6 install line and the design-review line neutrally. |
| ISS-007 | Push initial repo to GitHub | task | 0 | 2026-10-12 | 2026-10-12 | Pushed `main` to `shashank934602/secure-rag`. |
| ISS-006 | Spec 01 chunk size: "~800 tokens" vs `RecursiveCharacterTextSplitter` (counts characters) | question | 1 | 2026-10-12 | 2026-10-12 | Tokens via `tiktoken`; 400 tokens / 50 overlap, per page, configurable (spec 01 D1, D13). |
| ISS-009 | Phase 1 slice 1: sample corpus + golden set | task | 1 | 2026-10-12 | 2026-10-12 | 11 documents (10 MD + 3-page PDF, ~5.9k tokens, 23 chunks) and 10-question golden set; reviewed and approved by user. |
| ISS-010 | Phase 1 slice 2: load MD + PDF, chunk per page (400/50 tokens) | task | 1 | 2026-10-12 | 2026-10-12 | `app/ingestion/loaders.py` + `chunking.py`, typed `Page`/`Chunk` in `app/domain.py`; 10 tests; real corpus → 11 docs, 13 pages, 23 chunks. |
| ISS-011 | Phase 1 slice 3: embeddings factory + in-memory top-5 search | task | 1 | 2026-10-12 | 2026-10-12 | `make_embeddings('provider:model')` + `ChunkIndex.search` with cosine scores; 6 offline tests. Real-corpus check pending on ISS-014. |
| ISS-012 | Phase 1 slice 4: answer + citation validation (TDD, fake LLM) | task | 1 | 2026-10-12 | 2026-10-12 | `Answerer.answer(question) -> AnswerResult`; prompt `answer_v1` with the No-Answer sentence substituted from one constant; citations parsed (multi-id brackets), deduplicated, and checked against retrieved pages; config-only provider swap tested offline. 13 tests. |
| ISS-013 | Phase 1 slice 5: CLI (`--debug`) + live smoke test | task | 1 | 2026-10-12 | 2026-10-12 | `python -m app.cli "question" [--debug]`; exit 0 answered/No-Answer, 1 on error; 4 CLI tests; 2 live tests (`-m live`) written, currently fail on ISS-014. |
| ISS-014 | OpenAI account has no credits | bug | 1 | 2026-10-12 | 2026-10-15 | Replaced instead of paid: embeddings now Mistral `mistral-embed` (ADR-0005); swap check uses Mistral chat. ISS-001's choice is superseded by ADR-0005. |
| ISS-015 | Citation parser rejects the model's real citation formats: full-width `【doc_id:page】` and chunk ids `doc_id:page:index` | bug | 1 | 2026-10-13 | 2026-10-19 | Learner's warm-up exercise 1: `_BRACKET` accepts `[ ]` and `【 】`; `_REFERENCE` accepts an optional `:index`, which is ignored. 10 tests in `tests/test_citations.py` built from real replies. |
| ISS-018 | Mistral chat swap fails: `mistral-small-latest` returns 429 on every call | bug | 1 | 2026-10-19 | 2026-10-19 | Not our code: on this free-tier key `mistral-small-latest` and `mistral-medium-latest` are rate-limited (429) and `mistral-large-latest` is not allowed (403). `ministral-8b-latest` and `open-mistral-nemo` work. The swap model is now `ministral-8b-latest` (spec 01 D8, test). |
| ISS-020 | Phase 2 S1: Postgres in Docker, migrations, seed tenant, `rag_app` role, DB test fixture | task | 2 | 2026-10-21 | 2026-10-22 | `docker-compose.yml` (pgvector pg16 on 127.0.0.1:5433), Alembic raw-SQL migration `0001` (4 tables, `vector(1024)`, HNSW cosine index, seed Aldermoor), `rag_app` non-superuser/no-BYPASSRLS with password from `DATABASE_URL`; 11 `db` tests via testcontainers. |
| ISS-021 | Phase 2 S2: ingest command (`python -m app.ingest`) | task | 2 | 2026-10-21 | 2026-10-22 | `app/ingest.py`: SHA-256 fingerprint per file (unchanged → skipped, zero embedding calls), one transaction per document (embed first, then upsert + replace chunks), deleted files removed, failures reported and rolled back (exit 1). 9 `db` tests. Dev DB: 11 documents / 23 chunks with `mistral-embed`; second run 0.7 s, nothing re-embedded. |
| ISS-022 | Phase 2 S3: `Retriever` protocol + `PgRetriever` query; CLI on Postgres | task | 2 | 2026-10-21 | 2026-10-29 | Query written by the assistant at the learner's request (concepts-first; the learner explains it back). 14/14 search tests, plus end-to-end db tests (only the question is embedded). `build_db_answerer`; the CLI uses Postgres when `DATABASE_URL` is set. Real run: same top-5 scores as in memory, 1 Mistral text instead of 24, 5.1 s → 3.2 s. |
| ISS-023 | Phase 2 S4: FastAPI `POST /v1/ask` + `GET /healthz` | task | 2 | 2026-10-21 | 2026-10-29 | `app/main.py` (`create_app` with injectable build and health check): 1–1,000-char validation → 422; failures → 503 with a generic message; logs hold the error type + `request_id` only; answerer built once at start-up; 127.0.0.1 only. 9 offline + 1 db test. Real curl runs: 200 answer, 200 no-answer, 422, 503 with the DB stopped. |
| ISS-027 | API failed forever after a database restart while `/healthz` said OK | bug | 2 | 2026-10-29 | 2026-10-29 | Found by stopping and restarting the dev database. Cause: one connection opened at start-up, killed by the restart. Fix: `make_pool` (psycopg-pool, connections checked before use); `PgRetriever` accepts a connection or a pool. Regression test terminates the app's connections and asks again. |
| ISS-028 | API start-up with the database down retried forever with no hint (looked like "not starting") | bug | 2 | 2026-10-29 | 2026-10-29 | Reported by the learner. `make_pool` now waits at most 5 s, then fails with "Cannot reach the database at host:port. Is Docker running? … docker compose up -d" (no password in the message). Start-up checklist added to `lessons/02-databases-and-apis.md`. |
