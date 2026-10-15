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

## Design — 2026-10-10

### Added

- `docs/architecture.md`: HLD, ingestion, LangGraph query flow, latency budget, guardrails, data model, API, eval pipeline, deployment, invariants, limitations.
- ADR-0001 Postgres + pgvector as the single store.
- ADR-0002 ACL copied onto chunks, enforced by RLS and query filter.
- ADR-0003 No token streaming; output guard sees the full answer first.
- ADR-0004 Store raw text; mask PII at query time by permission.
- `GLOSSARY.md`, `plan.md`, context files, and the Phase 1 spec.
