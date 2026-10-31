# Progress Tracker

Update after every meaningful change. Describe what is actually built, not what is intended.

## Current phase

**Phase 3 — better retrieval + LangGraph** (`context/feature-specs/03-hybrid-retrieval-rerank-langgraph.md`): spec written and sliced S1–S4 (ISS-030 … ISS-033) on 2026-10-31. **Phase 2 done: released `v0.2.0` on 2026-10-30** with a committed baseline (`eval/baselines/phase2.json`). Phase 1 released `v0.1.0` on 2026-10-19.

Phase 1 history: basic RAG pipeline (`context/feature-specs/01-basic-rag-pipeline.md`). Spec grilled and decided (D1–D16).
All 5 slices built; 45 offline tests pass; first real run done with Mistral embeddings (ISS-014 closed); ISS-015 fixed by the learner (2026-10-19). Golden rerun passed (6/7, 3/3); live tests 2/2; Mistral chat swap works with `ministral-8b-latest` (ISS-018). Phase 1 closed. **Phase 2 started** (decisions agreed, spec 02). Phase 0 leftover: ISS-005.

## Completed

- **Phase 3 S3 — LangGraph flow** (2026-10-31, ISS-032)
  - Answering runs as a compiled LangGraph graph (`app/answering/graph.py`); invalid citations get one retry with a correction note; below-threshold retrieval skips the LLM. 104 offline, 47 db, 4 live tests.
- **Phase 3 S2 — reranker** (2026-10-31, ISS-031)
  - `CrossEncoderReranker` (`BAAI/bge-reranker-base`, local, MPS; first download ~1 GB / 5 min). `Answerer(reranker=, candidates=, threshold=)`: search `candidates`, rerank to `top_k`; below the threshold → No-Answer without an LLM call. `Answerer.retrieve()` is what the eval scores.
  - Calibration on the golden set: answerable best scores reach down to 0.049 and unanswerable up to 0.479, so there's no clean threshold; it stays 0.0 (ISS-034). Settings default `rerank=False` until the S4 eval.
- **Phase 3 S1 — keyword + hybrid search** (2026-10-31, ISS-030)
  - Migration `0002`: `chunks.content_tsv` (generated full text) + GIN index; dev DB at `0002 (head)`, 23/23 chunks indexed.
  - `PgRetriever` modes `dense` / `keyword` / `hybrid` (RRF, 20 candidates per list); `Settings.retrieval_mode` (default still `dense`) and `candidates`.
  - Real ranks for the failing questions: g17's handbook 7th → 1st (exact words "gift", "declare"); the org chart drops (g06 6th → 10th, g17 3rd → 6th): it's a two-hop page.
- **Phase 2 closed — `v0.2.0`** (2026-10-30, ISS-026)
  - `python -m eval.run --save-baseline`: 20 golden questions through the API with real models and Postgres. Baseline: recall@5 0.929, MRR 0.917, key-fact score 0.857, answered 12/14 (misses g06, g17: org chart not retrieved, ISS-017), No-Answer 6/6, p50 9.5 s / p95 13.3 s (free-tier throttling, ISS-029), 0 errors.
  - Tests: 90 offline, 39 db, 2 live.
- **Phase 2 S6 — eval metrics** (2026-10-29, ISS-025)
  - `eval/metrics.py`: recall@k, reciprocal rank / MRR, key-fact score with normalisation of real model output, No-Answer correctness, latency percentiles, `summarise`. 22 tests; 86 offline tests in total.
- **Phase 2 S5 — golden set** (2026-10-29, ISS-024)
  - `eval/datasets/golden.jsonl`: 20 entries (14 / 6), `key_facts` on every answerable entry; `scripts/check_golden.py` (`uv run python -m scripts.check_golden`) proves each key fact is on an expected page.
  - Real preview of the 10 new questions: 9/10 correct; g17 fails like g06 (org chart not retrieved, ISS-017).
- **Phase 2 S4 — web API** (2026-10-29, ISS-023, ISS-027)
  - `app/main.py`: `POST /v1/ask` → `{answer, citations[{doc_id, page, source}], request_id, status}`; 422 on invalid input; 503 with a generic message on failure; `GET /healthz` (DB `SELECT 1`) 200/503; answerer built once; run with `uvicorn app.main:app --host 127.0.0.1`.
  - Bug found and fixed: after a DB restart `/v1/ask` failed forever (single start-up connection). Now a checked connection pool (`make_pool`, psycopg-pool).
  - Tests: 55 offline, 39 db, 2 live. Real curl runs verified 200 / 200 no-answer / 422 / 503, recovery after a DB restart, and no question text in logs.
- **Phase 2 S3 — Postgres search** (2026-10-29, ISS-022)
  - `PgRetriever` (`app/retrieval/pg_search.py`): one SQL query, filtered by tenant, `is_active`, and role overlap, ordered by `<=>` (HNSW), `score = 1 - distance`. Written by the assistant at the learner's request; the learner explains it back.
  - `build_answerer(…, retriever=)`, `build_db_answerer(settings)`; `Settings.roles`; the CLI uses Postgres when `DATABASE_URL` is set, otherwise in memory.
  - Tests: 46 offline, 37 db, 2 live. Real run: same top-5 scores as in memory; 1 embedding per question instead of 24; 5.1 s → 3.2 s.
- **Phase 2 S2 — ingest** (2026-10-22, ISS-021)
  - `python -m app.ingest`: per-file SHA-256 fingerprint; unchanged → skipped; new/changed → chunk, embed (outside the transaction), then upsert document (version + 1) and replace its chunks in one transaction; removed files deleted (chunks cascade); failures rolled back and reported, exit 1.
  - `connect(url, autocommit=)`; `Settings.tenant`; test fake `CountingEmbeddings`.
  - Tests: 20 `db` (9 new), 45 offline. Dev DB: 11 documents / 23 chunks, `vector_dims` 1024, `mistralai:mistral-embed`; 1st run 9.6 s, 2nd run 0.7 s with no embedding calls.
- **Phase 2 S1 — database** (2026-10-22, ISS-020)
  - `docker-compose.yml`: `pgvector/pgvector:pg16` (pgvector 0.8.7) on `127.0.0.1:5433`, data in volume `pgdata`, healthcheck.
  - `db/`: Alembic with raw-SQL migration `0001_initial_schema` — `tenants`, `users`, `documents`, `chunks` (`vector(1024)`, HNSW `vector_cosine_ops`, `(tenant_id, is_active)` index), seed tenant Aldermoor `{employee}`, role `rag_app` (no superuser, no BYPASSRLS, row-level CRUD only).
  - `app/db.py` `connect(url)` with pgvector types; `Settings.database_url` / `database_admin_url`.
  - Tests: 11 `db` tests (`uv run pytest -m db`, testcontainers); 45 offline tests still pass. Dev database migrated to `0001 (head)`; app logs in as `rag_app`, cannot drop tables.
- **Phase 1 closed — `v0.1.0`** (2026-10-19)
  - `uv run pytest -m live`: 2 passed. Swap: `CHAT_MODEL=mistralai:ministral-8b-latest` answered g01 with a valid citation and gave No-Answer for an off-corpus question, with no code change.
- **Warm-up exercise 1: citation formats** (2026-10-19, ISS-015)
  - Learner fixed `app/answering/citations.py`: accepts `【doc_id:page】` and `doc_id:page:index`. `tests/test_citations.py` has 10 tests from real model replies, and the full suite is 45 passed.
  - Golden rerun on real models: **6/7 answerable answered** (was 2/7), 3/3 No-Answer correct; only g06 missed (retrieval, ISS-017).
- **Mistral switch + first real run** (2026-10-15)
  - `EMBEDDING_MODEL` default `mistralai:mistral-embed` (1024-d), `langchain-mistralai` added; ADR-0005; 35 offline tests pass.
  - First real run (Mistral embeddings + Groq `gpt-oss-120b`): expected page in top-5 for 10/11 sources; answered 2/7 answerable; 3/3 trick questions → No-Answer. Failures: 4 × citation format (ISS-015), 1 × retrieval miss (ISS-017). Groq latency up to ~14 s on the free tier.
  - Mistral chat swap reached the API but hit the free-tier rate limit; to re-run after ISS-015.
  - Phase 2 decisions D0–D11 agreed (spec 02).
- **Learning setup** (2026-10-13)
  - Agreed approach in `plan.md` §0: learning-first, 10–12 h/week, < $20, learner writes core parts, lesson → build against tests → walkthrough + quiz + experiment; ~13–15 weeks.
  - Teaching-first rules in `AGENTS.md` and `context/ai-workflow-rules.md`.
  - Guides: `docs/project-guide.md`, `docs/code-structure.md` (13 diagrams). Lesson 1: `lessons/01-how-applied-ai-works.md` + `lessons/01_experiments.py` (run against Groq).
  - Learning log `lessons/learning-log.md` + session-start reminder (`scripts/learning_reminder.py`; hook in local `.claude/settings.json`).
  - `docs/production-plan.md` written; production decisions tracked as ISS-016.
  - Lesson 1 experiment 3 found ISS-015: `gpt-oss-120b` cites with `【…】`, which the parser rejects.
- **Phase 1 slice 5 — CLI + live test** (2026-10-12, ISS-013)
  - `app/cli.py`: `main(argv, build=...)`; answer + `Sources:`; `--debug` shows status, prompt version, retrieved chunks with scores; errors → one-line message, exit 1 (`--debug` shows the traceback).
  - `tests/test_live.py` (`-m live`): g01 answered with a correct source, g10 No-Answer. Currently errors with OpenAI `insufficient_quota`.
- **Phase 1 slice 4 — answer + citations** (2026-10-12, ISS-012)
  - `app/answering/answer.py`: `Answerer.answer(question) -> AnswerResult` (status, answer, citations, retrieved, prompt_version); `build_answerer(settings)`.
  - `app/answering/citations.py`: parse `[doc_id:page]` (also `[a:1, b:2]`), validate against retrieved pages.
  - `app/prompts/answer_v1.md`; `NO_ANSWER` constant substituted into it.
  - Tests: 29 passing offline (fake chat model + keyword embeddings). Not yet run against real models (ISS-014).
- **Phase 1 slice 3 — embeddings + search** (2026-10-12, ISS-011)
  - `app/retrieval/embeddings.py`: `make_embeddings(model)` via `init_embeddings`, full dimension.
  - `app/retrieval/search.py`: `ChunkIndex(chunks, embeddings).search(question, k)` → `ScoredChunk`s, best first.
  - `get_settings()` loads `.env` into the environment so clients find their keys.
  - Tests: 16 passing offline. Real embeddings not yet run: OpenAI returns `insufficient_quota` (ISS-014). Groq chat verified working.
- **Phase 1 slice 2 — loading + chunking** (2026-10-12, ISS-010)
  - `app/ingestion/loaders.py`: `load_pages(folder)`; MD = page 1, PDF = one page per PDF page (1-based, empty pages skipped); hidden files ignored; other types and duplicate doc ids raise.
  - `app/ingestion/chunking.py`: `chunk_pages(...)`; per-page token chunks via `tiktoken` `cl100k_base`.
  - `app/config.py` (`Settings`, `get_settings()`), `app/domain.py` (`Page`, `Chunk`).
  - Tests: 10 passing (`uv run pytest`), ruff clean. Real corpus: 11 documents, 13 pages, 23 chunks.
- **Phase 1 slice 1 — sample corpus + golden set** (2026-10-12, ISS-009)
  - `data/sample/`: employee handbook; annual leave, sickness absence, expense, IT security, health and safety, remote work policies; CleanFleet and TrackLine contracts; org chart (Markdown); SwiftParts contract (3-page PDF). ~5,900 tokens, 23 chunks at 400/50.
  - Fake data only: `aldermoor.example.com` / `*.example.com` emails, `555-01xx` phones, `AF-` employee ids.
  - `eval/datasets/golden.jsonl`: 10 entries; every expected fact checked against its cited page; near-miss topics confirmed absent.
- **Phase 0 — Setup** (2026-10-12)
  - Own Git repo (`main` branch) in this folder, pushed to `https://github.com/shashank934602/secure-rag`.
  - `uv` project, Python pinned to 3.12 (`.python-version`, `requires-python = ">=3.12,<3.13"`).
  - Phase 1 deps: `langchain`, `langchain-core`, `langchain-openai`, `langchain-groq`, `langchain-text-splitters`, `pypdf`, `pydantic`, `pydantic-settings`, `python-dotenv`. Dev: `pytest`, `ruff`.
  - `.env` (gitignored) with Groq, OpenAI, Hugging Face, Google, Mistral keys; `.env.example` committed.
  - Check passes: `uv run python -c "import langchain"` (langchain 1.4.4 on Python 3.12.14).
  - Tracking: `AGENTS.md` (agent entry point, Arch-AI pattern), `context/issue-tracker.md`, `CHANGELOG.md`.
- **Design** (2026-10-10)
  - `docs/architecture.md`: HLD, ingestion, LangGraph flow, sequence, latency budget, guardrails, data model, API, eval pipeline, deployment, invariants, limitations.
  - Independent design review applied: latency/streaming contradiction, ACL staleness + RLS, PII masking moved to query time, audit hash chain + start row, tenant-scoped audit/upload authorization, cache rules, structural injection controls, hybrid search, early eval harness.
  - ADRs 0001–0004, `GLOSSARY.md`, context files.

## Decisions (Phase 0, from `plan.md` §9)

- Embedding model: OpenAI `text-embedding-3-small`, 1536-d → `vector(1536)`. `bge-small-en-v1.5` (384-d) is the offline fallback.
- Reranker hardware: CPU / Apple MPS on the M4; no GPU.
- Sample corpus: synthetic, LLM-generated, hand-edited; two tenants; fake PII; canary strings in tenant B.
- Separate repo: yes — `shashank934602/secure-rag` (public).
- Main chat model: Groq `openai/gpt-oss-120b`.
- Grounding judge: small model from a different family (Llama or Gemini Flash).

## Open questions

Tracked in `context/issue-tracker.md`.

## Next steps

1. Lesson 1 questions → warm-up exercise 1 (ISS-015, citation brackets).
2. ISS-014 (waiting on user to add OpenAI credits — decision (a)): then run the CLI on the golden questions and `uv run pytest -m live`; if all spec checks pass, release `v0.1.0`.
2. ISS-005: resolve the workflow-skills question (Phase 1 uses the available `grilling` / `tdd` / `code-review` skills meanwhile).
