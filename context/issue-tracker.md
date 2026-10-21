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
