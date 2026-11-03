# Changelog

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## How to use

- Add entries under **Unreleased** in the same commit as the change, grouped as
  **Added** · **Changed** · **Fixed** · **Removed** · **Security**.
- One line per change, written for a reader of the repo; end with issue ids where relevant (`ISS-006`).
- Anything touching retrieval, guards, or prompts includes the eval delta (from Phase 2 on).
- **Releases follow phases:** when a phase's "Done when" passes, rename **Unreleased** to
  `## [0.N.0] — YYYY-MM-DD — Phase N: <name>`, tag the commit `v0.N.0`, and start a new empty **Unreleased**.

## [Unreleased]

### Changed

- `/v1/ask` and `PATCH …/acl` now write the audit trail: a request record at the start (HMAC + redacted text, never raw), then the outcome, sources, every guard decision, and per-step timings in one transaction; access changes are audited in their own transaction; if the audit can't be written, the request is refused (503) (ISS-051).
- The answering graph times every step (`AnswerResult.timings`); `AUDIT_HMAC_KEY` added to `.env.example`.

### Added

- Audit trail storage (migration `0005`): `requests`, `request_sources`, and `audit_events` chained per tenant with SHA-256 (`app/audit/chain.py`, `app/audit/log.py`); append-only for every role (triggers on UPDATE, DELETE, TRUNCATE); `verify` names the first edited or missing event; auditor user `audrey@aldermoor.example.com` (ISS-050).
- Phase 6 spec (`context/feature-specs/06-audit-observability.md`), ISS-050 … ISS-054; glossary: request record, hash chain.

## [0.5.1] — 2026-11-03 — Fixes from the independent test of v0.5.0

The tester's report (`docs/test-reports/v0.5.0.md`): **release with known issues, no critical or high findings**; suites
207 offline / 77 db / 7 live, `eval.guards` and `eval.leakage` match the 0.5.0 claims. Triage: T-1, T-3, T-4, T-5 fixed here;
T-6 → ISS-055; T-8, T-9 → ISS-056; T-7 is ISS-048.

### Fixed

- OpenAPI now documents every error response: 401/413/503 on `/v1/ask`; 401/403/404/413/503 on the ACL route; 503 on `/healthz` (T-1).
- Request bodies over 16 KB are refused with 413 before they are read (a 5 MB question used to be parsed and echoed back); validation errors no longer echo the input; `HEAD /healthz` works (T-3).
- The generator call has a 30 s timeout and one retry (`chat_timeout_s`); a network failure no longer hangs a request (T-4).
- Every 503 carries `Retry-After: 30`; `eval.leakage` retries a probe once after a provider error and reports probes that couldn't run (T-5).

### Added

- `docs/test-reports/`: every phase's independent test report and its triage.

## [0.5.0] — 2026-11-02 — Phase 5: guardrails

Phase 5 checks pass: every guard has tests, including fail-closed tests for each model-backed guard. Early numbers
(`python -m eval.guards`): **45/50 attacks blocked (95% CI 79–96%)**, **3/50 benign questions refused (2–16%)**;
role-play is the weak spot (4/8, ISS-048). With all guards on, the golden set matches Phase 4 (12/14 answered, key
facts 0.857, No-Answer 6/6, 0 input-guard refusals; `eval/baselines/phase5.json`), and `eval.leakage` finds 0 leaks,
with the "ignore your rules" probe now refused. The real judge rejects the Concept 6 bluff. Known: the judge
rejects ~1 in 5 correct derived answers (ISS-049); the poisoned-document case is not a guard problem (ISS-019).
The learner's explain-back is pending (build now, study later).

### Changed

- Grounding judge prompt `judge_v2`: claims derived directly from stated facts (comparisons, simple sums) count as supported (ISS-049).
- `docs/architecture.md` §2/§6: personal-data detection is our pattern detector with checksums, not Presidio; work contacts aren't masked.

### Added

- Grounding judge: Mistral `ministral-8b-latest` (a different family from the generator) checks every claim against the cited chunks (prompt `judge_v1`); unsupported answers get one retry naming the claims, then No-Answer; any judge failure refuses (503). Settings `grounding_judge`, `judge_model`, `judge_timeout_s` (ISS-045).
- Output checks on every answer: links, images, HTML, and URLs removed; secrets redacted; sensitive personal data redacted for users without `pii:read`; the detector handles narrow spaces and non-breaking hyphens (ISS-044).
- Context guard: drops chunks flagged as prompt injection and masks sensitive personal data (IBAN, UK bank account, NI number, card, UK mobile, personal email) for users without `pii:read`; ingest records `pii_types` and `injection_score` and quarantines flagged documents; migration `0004` (ISS-043).
- Input guard: pattern rules + local prompt-injection classifier (`protectai/deberta-v3-base-prompt-injection-v2`); attacks are refused (`status: refused`) before any search or LLM call; a failing guard returns 503 (ISS-041, ISS-042).
- Adversarial (50) and benign (50) sets; `python -m eval.guards` reports block and false-refusal rates with 95% Wilson intervals: 45/50 blocked, 3/50 falsely refused (ISS-042, ISS-048).

## [0.4.0] — 2026-11-02 — Phase 4: auth, tenants, and access control

Phase 4 checks pass: with no `WHERE tenant_id`, row-level security still returns only the scoped tenant's rows;
`python -m eval.leakage` finds **0 leaks** in 9 probes (cross-tenant, cross-role, canary requests, an injection) with
2/2 positive controls; the golden set scores exactly as in Phase 3 (recall@5 0.929, MRR 1.000, key facts 0.857,
12/14 answered, 6/6 No-Answer). Tests: 126 offline, 75 db, 4 live. Deferred: upload + jobs (ISS-039), rate
limiting (ISS-040). The learner's explain-back is pending (build now, study later).

### Added

- Leakage check `python -m eval.leakage`: probes as an Aldermoor employee for Northgate and HR-only data, fails on any canary or forbidden document in sources or answers, with positive controls; Phase 4 baseline `eval/baselines/phase4.json`; `lessons/04-access-control.md` (ISS-038).
- `PATCH /v1/documents/{doc_id}/acl`: change who can read a document (needs the `uploader` permission); document and chunks change in one transaction; another tenant's document is a 404 (ISS-037).

### Changed

- `POST /v1/ask` now requires `Authorization: Bearer <token>` and answers as that user (their tenant and roles); 401 without a valid token (ISS-036).

### Added

- JWT access tokens (`app/auth.py`, `pyjwt`): only user id, tenant id, and expiry in the token; roles and permissions read from the database on every request; `python -m app.auth token`; `JWT_SECRET` in `.env.example` (ISS-036).
- Row-level security on documents, chunks, and users (migration `0003`), with a per-transaction tenant scope; second tenant Northgate Haulage with canary documents; HR-only Aldermoor document; seeded users with roles and permissions; access scope through search and answering; `python -m app.ingest --tenant --folder --roles --collection` (ISS-035).

## [0.3.0] — 2026-10-31 — Phase 3: hybrid retrieval, reranking, LangGraph

Phase 3 check passes: hybrid + rerank beats dense-only on ranking and loses nothing. Three runs on the same day, 20 golden
questions, real models (`eval/baselines/phase3.json` = hybrid + rerank):

| Metric | Dense | Hybrid | Hybrid + rerank |
|--------|------:|-------:|----------------:|
| recall@5 | 0.929 | 0.929 | 0.929 |
| MRR | 0.917 | 0.964 | **1.000** |
| key-fact score | 0.857 | 0.857 | 0.857 |
| answered | 12/14 | 12/14 | 12/14 |
| No-Answer accuracy | 6/6 | 6/6 | 6/6 |

g06 and g17 still fail: they need the org chart, a two-hop page no single search finds (ISS-017). Latency isn't comparable
across runs (free-tier throttling, ISS-029). Defaults are now `retrieval_mode=hybrid`, `rerank=true` (threshold off, ISS-034).
The learner's explain-back is pending (build now, study later).

### Changed

- Defaults: `retrieval_mode=hybrid`, `rerank=true`; the reranker model loads on first use (ISS-033).
- `python -m eval.run --save-baseline NAME` writes `eval/baselines/NAME.json` (ISS-033).

### Changed

- Answering runs as a LangGraph state machine (`app/answering/graph.py`); invalid citations now get **one retry** with a correction note before a No-Answer; the model's own No-Answer is final; dep `langgraph` (ISS-032).

### Added

- `lessons/03-better-retrieval.md`: Phase 3 concepts (keyword search, RRF, cross-encoders, thresholds, state machines) with real numbers.
- Local cross-encoder reranker (`BAAI/bge-reranker-base` via `sentence-transformers`) behind a `Reranker` protocol; `Answerer` reranks candidates to top-k, with an optional relevance threshold that returns No-Answer without calling the LLM; settings `rerank`, `reranker_model`, `rerank_threshold`; eval reports record retrieval settings (ISS-031).
- Keyword search (migration `0002`: generated `content_tsv` + GIN index) and hybrid search fused with Reciprocal Rank Fusion; `PgRetriever(mode=dense|keyword|hybrid)`, `Settings.retrieval_mode`, `candidates` (ISS-030).

## [0.2.0] — 2026-10-30 — Phase 2: Postgres, API, and a baseline eval

Phase 2 checks pass: 90 offline, 39 db, and 2 live tests; golden set valid (20 questions); `/v1/ask` and `/healthz` verified with curl.

**Baseline** (`eval/baselines/phase2.json`, Mistral `mistral-embed` + Groq `gpt-oss-120b`, prompt `answer_v1`, 400/50 chunks, top 5):

| Metric | Value |
|--------|------:|
| recall@5 (answerable) | 0.929 |
| MRR | 0.917 |
| key-fact score | 0.857 |
| answered (answerable) | 12 / 14 |
| false refusals | 2 (g06, g17: org chart not retrieved, ISS-017) |
| No-Answer accuracy (unanswerable) | 6 / 6 |
| latency p50 / p95 | 9.5 s / 13.3 s (inflated by free-tier throttling, ISS-029) |

The learner's explain-back of the S3–S6 code is still pending (build now, study later; see `lessons/study-companion-context.md`).

### Changed

- Docker image pinned to `pgvector/pgvector:0.8.7-pg16` (was the floating `pg16` tag) in Compose and the test fixture, so every machine gets the same database version.

### Fixed

- Starting the API with the database down now fails within about 5 s with a clear message ("Is Docker running? … docker compose up -d") instead of retrying forever (ISS-028).

### Added

- Eval runner `python -m eval.run [--save-baseline]`: the 20 golden questions through the API in-process (real models + Postgres), retried on failure, scored with `eval/metrics.py`; report to `eval/reports/` (gitignored), baseline to `eval/baselines/phase2.json` (ISS-026).
- `lessons/study-companion-context.md`: context pack for studying in a second chat.
- Eval metrics `eval/metrics.py`: recall@5, MRR, key-fact score (normalises real model spaces, hyphens, bold), No-Answer accuracy and false refusals, p50/p95 latency, `summarise` (ISS-025).
- Golden set grown to 20 questions with `key_facts`; `scripts/check_golden.py` validates every key fact against its source page (ISS-024).
- Web API `app/main.py`: `POST /v1/ask` (validated 1–1,000 chars, 422; generic 503 on failure; `request_id`) and `GET /healthz`; listens on 127.0.0.1 only; deps `fastapi`, `uvicorn`, dev `httpx` (ISS-023).
- Connection pool `make_pool` (psycopg-pool) checks connections before use, so the API recovers after a database restart (ISS-027).
- Postgres search `PgRetriever` (tenant, active, and role filters; HNSW cosine order) and `build_db_answerer`; the CLI answers from the database when `DATABASE_URL` is set, embedding only the question (ISS-022).
- Ingest command `python -m app.ingest`: fingerprints skip unchanged documents, one transaction per document, removed files deleted, failures rolled back and reported (ISS-021).
- Local Postgres + pgvector in Docker (`docker-compose.yml`, port 5433) and Alembic raw-SQL migrations in `db/`: tenants, users, documents, chunks with `vector(1024)` and an HNSW cosine index; seed tenant; non-superuser `rag_app` role (ISS-020).
- Database tests marked `db` run against a throwaway container (`uv run pytest -m db`); new deps `psycopg`, `pgvector`, `alembic`, dev `testcontainers` (ISS-020).
- `lessons/02-databases-and-apis.md`: S1 section — databases, Docker, migrations, least privilege.
- Phase 2 spec completed: implementation, layout, 7 slices (ISS-020 … ISS-026), scope limits, done checks. Docker Postgres on port 5433.
- Glossary: content hash, ingest, retriever, baseline, key fact, recall@5, MRR, migration, app role.
- `lessons/01b-rag-concepts-and-functions.md`: the eight concepts behind the pipeline (RAG, tokens and chunking, embeddings, retrieval, prompt, generation and output checks, evaluation, swappable design), plus every function with a real input and output from our corpus.

## [0.1.0] — 2026-10-19 — Phase 1: basic RAG pipeline

All Phase 1 checks pass: 45 offline tests, 2 live tests, golden set 6/7 answered + 3/3 No-Answer on real models, and the chat provider swapped (Groq → Mistral) with config only.

### Added

- Project setup: `uv` project pinned to Python 3.12, Phase 1 dependencies, `uv.lock`.
- `.gitignore` and `.env.example`; secrets stay in an untracked `.env`.
- `AGENTS.md` as the agent entry point (read order, tracking rules, git rules, commands).
- `context/issue-tracker.md` and this changelog for tracking work and changes.
- Phase 0 decisions recorded: embedding model, reranker hardware, sample corpus, separate repo (ISS-001–ISS-004).
- Repository published at `shashank934602/secure-rag` (ISS-007).

### Changed

- Docs describe agent tooling neutrally (ISS-008).
- Phase 1 spec rewritten with grilled decisions D1–D16; chunks are 400 tokens / 50 overlap per page, measured with `tiktoken` (ISS-006).
- Glossary: added **Doc id** (filename slug used in citations).

### Added (Phase 1)

- Sample corpus for Aldermoor Freight Ltd in `data/sample/`: 10 Markdown documents and a 3-page PDF contract (~5.9k tokens, 23 chunks), with fake contact data only (ISS-009).
- `scripts/build_sample_pdf.py` builds the PDF from `scripts/sample_sources/`, one source section per page; `fpdf2` added as a dev dependency (ISS-009).
- Golden set `eval/datasets/golden.jsonl`: 10 questions, 7 answerable (2 need two documents), 3 unanswerable (ISS-009).
- Loading and chunking: Markdown and PDF files → `Page` records with doc id and 1-based page → 400-token chunks (cl100k, 50 overlap) with ids `doc_id:page:index`, never spanning pages (ISS-010).
- `app/config.py` settings (`pydantic-settings`), `app/domain.py` glossary types, pytest and ruff configuration (ISS-010).
- Embeddings factory `make_embeddings("provider:model")` and in-memory `ChunkIndex` returning top-k chunks with cosine scores; `numpy` added (ISS-011).

- Answering: prompt `answer_v1`, `Answerer.answer(question)` returning `AnswerResult`; any missing or unretrieved citation, or the No-Answer sentence, gives a No-Answer (ISS-012).
- `build_answerer(settings)` wires corpus, embeddings, and the chat model named in config; swapping provider needs only `CHAT_MODEL` (ISS-012).
- CLI `python -m app.cli "question" [--debug]`: answer plus sources; `--debug` adds status, prompt version, and retrieved chunks with scores (ISS-013).
- Live smoke tests against real models, run only with `uv run pytest -m live` (ISS-013).

- `docs/project-guide.md`: plain-language guide to the project — the problem, every concept, all phases, what is built, how we work, the agreed plan.
- `docs/code-structure.md`: code structure with 13 diagrams — layers, imports, data shapes, start-up and question workflows, decision rules, tests, development loop.

- `lessons/01-how-applied-ai-works.md` and `lessons/01_experiments.py`: lesson 1 with five runnable experiments (tokens, no documents, RAG by hand, temperature, prompt injection).
- Agreed approach recorded: learning-first goal, budget, cut order, timeline (`plan.md` §0); teaching-first workflow (`AGENTS.md`, `context/ai-workflow-rules.md`).

- `lessons/learning-log.md`: daily learning journal (where / what / how / can explain / unclear / next) with entries for 2026-10-12 and 2026-10-13; `scripts/learning_reminder.py` prints the rule and latest entry for session start.
- `docs/production-plan.md`: production plan — decisions, readiness gates, stages A–F, don'ts, backup and disaster recovery, fallback plans, post-production operations (ISS-016).

### Changed (Phase 1–2)

- Embeddings switched from OpenAI to **Mistral `mistral-embed`** (1024-d) — one config line plus `langchain-mistralai`; ADR-0005; closes ISS-014. Model-swap tests now cover Mistral embeddings and chat.
- First real run on the golden set: search found the expected page for 10 of 11 sources; 2 of 7 answerable questions accepted (4 lost to ISS-015, 1 retrieval miss ISS-017); 3 of 3 trick questions correctly answered "I don't know".
- Phase 2 decisions recorded in `context/feature-specs/02-postgres-api-baseline.md`.

### Fixed (Phase 1)

- API keys in `.env` are now exported to the process environment, where model clients read them (ISS-011).
- Citations in the formats real models write, full-width `【doc_id:page】` and chunk ids `doc_id:page:index`, are now accepted; before, correct answers were thrown away as No-Answer (ISS-015). Golden set on real models: 6 of 7 answerable answered (was 2 of 7), 3 of 3 No-Answer.
- Provider-swap check uses `mistralai:ministral-8b-latest`; `mistral-small-latest` is rate-limited on the free tier (ISS-018).

## Design — 2026-10-10

### Added

- `docs/architecture.md`: HLD, ingestion, LangGraph query flow, latency budget, guardrails, data model, API, eval pipeline, deployment, invariants, limitations.
- ADR-0001 Postgres + pgvector as the single store.
- ADR-0002 ACL copied onto chunks, enforced by RLS and query filter.
- ADR-0003 No token streaming; output guard sees the full answer first.
- ADR-0004 Store raw text; mask PII at query time by permission.
- `GLOSSARY.md`, `plan.md`, context files, and the Phase 1 spec.
