# Learning Log

This is a **learning-by-doing** project. We are not just building — every session records
**where** we are, **what** was learned, and **how** it was learned, so nothing depends on anyone's
memory (human or AI).

## The rule

1. **Every working session gets an entry** — at least one per day we work, updated after each step.
2. **Read the latest entry before starting** — it says exactly where to pick up.
3. **Write in plain language**, for the learner reading it weeks later.
4. **Be honest**: record what was actually understood and what is still unclear — not what was planned.
5. **Newest entry at the bottom.** Never delete or rewrite old entries; add corrections as new lines.

## Entry template

```markdown
## YYYY-MM-DD — <short title>

**Where we are:** <phase / step / issue ids>

**What we learned:**
- <concept, in one plain sentence each>

**How we learned it:**
- <lesson, experiment, exercise, code written, bug found…> (files: `…`)

**What I can now explain:** <the learner's own understanding, in their words when possible>

**Still unclear / open questions:**
- <…>

**Next session starts with:** <the exact next step>
```

---

## 2026-10-12 — Setup, Phase 1 planned and built

**Where we are:** Phase 0 done; Phase 1 built (ISS-009 … ISS-013); blocked on OpenAI credits (ISS-014).

**What we learned:**
- A RAG assistant answers from private documents by *retrieving* relevant pieces and giving them to the model.
- The project's design: 9 phases, from a basic pipeline to access control, guardrails, audit trail, and an eval gate.
- `uv` manages the Python version (3.12) and exact package versions (`uv.lock`) so the project is reproducible.
- Decisions are made *before* building, in question rounds ("grilling"), and written into a spec.

**How we learned it:**
- Read and discussed the design docs (`plan.md`, `docs/architecture.md`, ADRs).
- Grilled Phase 1: 16 decisions recorded in `context/feature-specs/01-basic-rag-pipeline.md`.
- Built Phase 1 test-first in 5 slices (code written by the assistant this time): corpus of 11 documents,
  loading and chunking, embeddings and search, answering with citation checks, CLI. 33 offline tests.
- Set up the separate GitHub repo, the `shashank934602` identity for `~/Desktop/shashank/`, and tracking files
  (`context/issue-tracker.md`, `CHANGELOG.md`, `AGENTS.md`).

**What I can now explain:** not yet checked — the walkthrough of the code was started on 2026-10-13.

**Still unclear / open questions:**
- Real-model run blocked: OpenAI account has no credits (ISS-014; decision: add credits later).

**Next session starts with:** understanding what was built (walkthrough), and agreeing how to learn.

---

## 2026-10-13 — Learning plan agreed; Lesson 1: how applied AI works

**Where we are:** Phase 1 built, waiting on ISS-014. Learning approach agreed (`plan.md` §0). Lesson 1 done; its questions not yet answered.

**What we learned:**
- **Applied AI** = building safe, measurable products *around* models, not building models.
- An LLM predicts the **next token**, repeatedly; it produces *plausible* text, not *true* text.
- **Tokens** are the unit of price, speed, and limits (`Aldermoor` = 4 tokens, the leave policy = 510).
- A model knows nothing private; without documents it refuses or **hallucinates**.
- **RAG**: putting the right document in the prompt made the answer correct and cited.
- **Temperature 0** is *more* consistent, not perfectly consistent — so tests use fakes and quality is measured over many questions.
- **Instructions are just text**: a hidden line in a document made the model reply `BANANA` (prompt injection). A prompt rule fixed it this time, but a rule is a request, not a guarantee.
- **Chunking** (walkthrough stop ①): documents → pages → ~400-token chunks with 50-token overlap, never across pages.

**How we learned it:**
- Five experiments against the real Groq model: `lessons/01_experiments.py`, written up in `lessons/01-how-applied-ai-works.md`.
- Walkthrough stop ① with real chunks from the leave policy.
- Guides written: `docs/project-guide.md` (concepts, phases) and `docs/code-structure.md` (13 diagrams).
- Grilled the project itself: goal = learning; 10–12 h/week; < $20; learner writes core code; lesson → build against tests → walkthrough + quiz + experiment.

- Set up this **learning log** and an automatic reminder: `scripts/learning_reminder.py` runs at every session start and after context compression, so the rule and the latest entry are never lost.
- Wrote `docs/production-plan.md`: what "production" means, decisions, readiness gates, stages A–F, what not to do, backups (RPO/RTO, 3-2-1, restore drills), fallback plans, and post-production operations.

**Real bug found by learning:** the model cited `【annual-leave-policy:1】`; our parser only accepts `[…]`,
so a correct answer would become "I don't know". Fake-model tests missed it. Logged as **ISS-015**.

**What I can now explain:** pending — Lesson 1's three questions and the stop ① question (heading split
from its content) are unanswered.

**Still unclear / open questions:**
- Lesson 1 questions 1–3 (why models invent; why a prompt rule isn't enough; why not paste every document).
- Walkthrough stop ①: why a heading separated from its rules can hurt retrieval.
- Production decisions D-P1 … D-P8 (users, hosting, **hosting budget** beyond the < $20 AI budget) — not needed until after Phase 7 (ISS-016).

**Next session starts with:** answer the Lesson 1 questions → warm-up exercise 1: fix ISS-015 (citation brackets) yourself against tests.

---

## 2026-10-14 — Picking up: where are we?

**Where we are:** Phase 1 built (33 offline tests pass), not yet closed — waiting on OpenAI credits (ISS-014).
Learning track: Lesson 1 done; its questions and walkthrough stop ① still unanswered. Open: ISS-005, ISS-014, ISS-015, ISS-016.

**What we learned:** nothing new yet — session started with a status check. The session-start reminder
loaded this log automatically, so the rule survived the new session.

**How we learned it:** —

**What I can now explain:** pending (Lesson 1 questions).

**Still unclear / open questions:** same as 2026-10-13.

**Next session starts with:** answer the 3 Lesson 1 questions → warm-up exercise 1: fix ISS-015 yourself against tests.

---

## 2026-10-15 — Planning the next steps

**Where we are:** unchanged — Phase 1 built, not closed. Checked OpenAI today: still `insufficient_quota` (ISS-014).

**What we learned:** the order of work from here (below); nothing new technically yet.

**How we learned it:** reviewed the plan together.

**The plan agreed to discuss:**
1. Now (no credits needed): Lesson 1 questions → warm-up 1 (fix ISS-015 yourself against tests) → walkthrough stops ②–⑤ + quiz.
2. When credits are added: close Phase 1 (real golden-question run, live tests, provider swap, release `v0.1.0`).
3. Phase 2: lesson 2 → answer the Phase 2 decision round → build (you write Postgres search + eval metrics) → baseline score.

**What I can now explain:** pending (Lesson 1 questions).

**Still unclear / open questions:** Lesson 1 questions 1–3; stop ① question; Phase 2 decision round (10 questions, asked 2026-10-13, unanswered).

**Next session starts with:** answer the 3 Lesson 1 questions.

**Update (later on 2026-10-15) — Phase 2 kickoff:**
- Found a free alternative to OpenAI: the Mistral key works for embeddings (`mistral-embed`, 1,024 numbers per text). Lesson: the embeddings factory from Phase 1 makes switching provider a config change.
- Mistake to learn from: reading `.env` with the shell printed two API keys into the session log (the file has a space after `=`). Recommended rotating the OpenAI and Groq keys.
- Owner chose to start Phase 2 now; the Lesson 1 questions are deferred, not dropped.
- Phase 2 plan laid out: decisions (12) → lesson 2 → spec → 8 build steps (owner writes Postgres search + eval metrics) → baseline score. Docker Desktop is installed but not running.

**Next session starts with:** answer the Phase 2 decision round (or "all recommended").

**Update — first real run (2026-10-15):**
- **Switched embeddings to Mistral** with one config line (ADR-0005). An embedding = a list of 1,024 numbers per text; similar meaning → similar numbers.
- **First real run** on the 10 test questions: search found the right page 10/11 times; 3/3 trick questions → "I don't know" ✅; but only 2/7 real questions were answered.
- **Learned to diagnose before fixing:** looking at the model's *raw* replies showed two different failure types:
  - *output-format failure* (4 answers): the model was right, but cited `【doc:page】` or `doc:page:chunk`, and our checker threw the answer away (ISS-015);
  - *retrieval failure* (1 answer, g06): the org chart never reached the model, so "I don't know" was correct (ISS-017 → Phase 3).
- **Free tiers have rate limits:** Mistral returned "Rate limit exceeded"; Groq answers slowed to ~14 s.
- Warm-up exercise 1 set up: `tests/test_citations.py` (6 failing, 4 passing) — the learner fixes `app/answering/citations.py`.

**Next session starts with:** warm-up exercise 1 — make `uv run pytest tests/test_citations.py` all green.

---

## 2026-10-16 — Warm-up exercise 1: learning regex to fix the citation checker

**Where we are:** Phase 2 step 1 — Phase 1 closes once ISS-015 is fixed. Exercise in progress: `tests/test_citations.py` 6 failing / 4 passing.

**What we learned:**
- (2026-10-15, after the exercise felt too hard) **Regular expressions** from zero: plain characters, `\d` and `+`, character sets `[...]`, escaping with `\`, capture groups `( )`, optional `?`, non-capturing groups `(?: )`.
- How to read our two patterns: `_BRACKET` finds text inside brackets; `_REFERENCE` checks it looks like `doc-id:page`.
- Python check: the learner can read loops, lists, and `if` — fine to continue without a Python warm-up.

**How we learned it:** runnable one-line examples (`uv run python -c "import re; …"`), then hints on the real exercise (hint A requested).

**What I can now explain:** in progress.

**Still unclear / open questions:** writing the patterns independently (Steps A and B).

**Next session starts with:** finish Step A (`_BRACKET`) and Step B (`_REFERENCE`) until `uv run pytest tests/test_citations.py` is all green.

**Update (later on 2026-10-16): solution explained, ready to type**
- The learner asked for the solution to be explained. A demo compared the old and new patterns on sample text without touching the code:
  - Step A, `_BRACKET`: `[\[【]([^\[\]【】]+)[\]】]` means "`[` or `【`, then anything that isn't a bracket, then `]` or `】`". A set `[ ]` means "any one of these", so the new bracket is added beside the old one.
  - Step B, `_REFERENCE`: `(?::\d+)?` is added after the page number. It means "an optional `:number` that we don't keep". `doc:page:chunk` is accepted, but only the doc and page are kept.
  - Demo result: `【expense:2】` and `expense-policy:1:1` are now found, and `see section 4` is still rejected.
- Lesson: **be tolerant of harmless format differences in model output, but strict about what matters** (the document and page must still be ones we retrieved).
- `tests/test_citations.py` is committed while still red (6 failing). That is on purpose: it's the exercise.

**Next session starts with:** type the two patterns into `app/answering/citations.py` (lines 7–8). Then run `uv run pytest tests/test_citations.py -v` (expect 10 passed) and `uv run pytest`, and close ISS-015.

---

## 2026-10-19 — Picking up: status check

**Where we are:** Phase 2 step 1. Phase 1 closes once ISS-015 is fixed. Checked today: `app/answering/citations.py` still has the old patterns. `uv run pytest` gives 39 passed and 6 failed, and all 6 failures are the exercise tests. GitHub is in sync.

**What we learned:** nothing new yet. The session started with a status check.

**How we learned it:** —

**What I can now explain:** in progress (regex Steps A and B, explained 2026-10-16).

**Still unclear / open questions:** typing the two patterns independently.

**Next session starts with:** type the two patterns into `app/answering/citations.py` (lines 7–8). Then run `uv run pytest tests/test_citations.py -v` (expect 10 passed).

**Update (later on 2026-10-19): warm-up exercise 1 done ✅ (ISS-015 closed)**
- The learner typed both patterns. Results: `tests/test_citations.py` 10/10, full suite 45 passed, lint clean.
- Review notes: the patterns are correct, and the old formats (`[a:1]`, `[a:1, b:2]`, ordinary brackets ignored) still behave. Two tidy-ups: the stray blank line between the constants was removed, and the docstring now says why the pattern accepts `【】` and `:index`. A strange-looking regex deserves a comment saying why.
- **Lesson:** fake-model tests passed all along, but the real model writes things we didn't expect. Tests built from *real* outputs (here, verbatim replies) catch what made-up examples miss.

**Next session starts with:** rerun the 10 golden questions on the real models (expect about 6/7 answered), then the live tests and the Mistral chat swap, then release `v0.1.0`.

**Update — golden rerun after the fix (2026-10-19):**
- Real models (Mistral embeddings + Groq `gpt-oss-120b`), same 10 questions as 2026-10-15:
  - **Answerable questions answered: 6/7** (was 2/7). g01, g03, g04 and g05 were rescued by the citation fix, and the replies still use `【】` and `:1:1`.
  - **Trick questions answered with "I don't know": 3/3** (unchanged).
  - The only miss is g06: the org chart is not in the top 5 search results, so "I don't know" is the right reply (ISS-017, Phase 3).
- **Lesson:** a two-line fix in *output parsing*, not a better model, tripled the answer rate. Check where an answer is lost before blaming the model.

**Next session starts with:** live tests (`uv run pytest -m live`) and the Mistral chat swap, then release `v0.1.0`.

**Update — Phase 1 closed, `v0.1.0` released (2026-10-19):**
- Live tests: 2/2 pass on the real models.
- The Mistral chat swap failed with **429 "Rate limit exceeded"**, even for one call made alone. Diagnosed by testing each model separately: on our free key, `mistral-small` and `mistral-medium` are rate-limited, `mistral-large` is not allowed (403), and `ministral-8b` and `open-mistral-nemo` work. The swap check now uses `ministral-8b-latest` (ISS-018).
- **Lessons:**
  - Read the error code before changing code. 429 means too many requests, 403 means not allowed, and neither one is a bug in our code.
  - Free tiers are limited **per model**, so "my key works" doesn't mean "every model works".
  - The swap proves our design: we changed AI company with one setting, and the citation checks and No-Answer still worked.
- **Release:** a release is a named, tagged version (`v0.1.0`) of the code that we know works. We can always go back to it or compare against it.

**Next session starts with:** Phase 2, Lesson 2 (vector databases, SQL, Docker, APIs). Start Docker Desktop beforehand.

**Update — concepts before code (2026-10-19):**
- The learner asked to learn the *concepts* behind the codebase, not just code. From now on: idea first, with real numbers, and code only as "where it lives".
- Concepts covered, following one question through the system: RAG (open-book exam), tokens and chunking (overlap verified on real chunks), embeddings (1,024 numbers; "days off" ↔ "annual leave" scores 0.728, against 0.586 for a hotel sentence), and retrieval (top-k always returns something; the leave question's best score was 0.850, the unanswerable CEO question's only 0.692).
- Notes written: `lessons/01b-rag-concepts-and-functions.md`, with eight concepts and every function with a real example. Check questions have folded answers.

**Still unclear / open questions:** the learner's answers to the three check questions (why the CEO question isn't answered; why embeddings beat keywords; what 5,000-token chunks would break).

**Next session starts with:** answer the three check questions, then concepts 5–8 (prompt, generation and checks, evaluation, swappable design), then Lesson 2.

---

## 2026-10-21 — Picking up: concepts 1–4 check, then 5–8

**Where we are:** Phase 1 done (`v0.1.0`). Phase 2 not started; Lesson 2 comes next. Concept notes `lessons/01b-rag-concepts-and-functions.md` are written, and concepts 1–4 have been taught. The repo is clean and in sync.

**What we learned:**
- **Search finds what's close; it never decides what's present or true.** It always returns 5 chunks. "I don't know" comes from prompt rule 3 plus the citation checks.
- Embeddings capture **meaning, not spelling**: they were learned from how words are used, so "days off" ≈ "annual leave".
- Huge chunks blur many topics into one set of numbers, so every question looks a bit similar to every chunk.
- **Grounding:** our checks verify that a citation *exists* and points to a *retrieved* page, not that the page *supports* the claim. Demo: "The CEO earns £200,000 [expense-policy:1]" was **shown as an answer**. The fix is a grounding judge (Phase 5) and the faithfulness metric (Phase 7).

**How we learned it:** answered three check questions, got feedback, then a follow-up scenario tested with a scripted fake model on real search (3 bluffs, 1 got through).

**What I can now explain:** that we turn text into numbers to search, and that a cited answer gets returned. Partly: the learner first thought the checks verify "proof", and the demo corrected this. Still to firm up: *why* embeddings match meaning, and *who* decides "I don't know" (the model's rule and the checks, not search).

**Still unclear / open questions:** none raised. Watch for confusion between "close" (search) and "true" (grounding).

**Next session starts with:** concepts 5–8 (prompt, generation and checks, evaluation, swappable design), then Lesson 2.

**Update — Concept 5, the prompt (2026-10-21):**
- What the model reads for one question: 134 tokens of rules + 1,394 tokens of chunks; the question is only 10. Cost comes from `top_k` × chunk size.
- Real attacks on our pipeline: the **blunt injection** ("you are a pirate") was **resisted** (rule 4 worked this time). The **subtle poisoning** ("from 2026 everyone gets 40 days") **fooled it**, and the answer passed every check.
- Lessons: injection = hidden *commands*; poisoning = false *facts*. **Grounded ≠ true.** Defences for poisoning are about *who may add documents* and *which is authoritative*, not the prompt. Logged as ISS-019.

**Next session starts with:** the three Concept 5 check questions, then Concept 6 (generation and temperature).

**Update — implementation started: Phase 2 step 3, spec and slices (2026-10-21):**
- The learner asked to start building. We switched to **learn while building**: each slice opens with the concept it needs.
- Concept: a **spec** says what to build, how we know it's done, and what we won't do. A **slice** is a small, end-to-end, testable piece that ends green and pushed, so mistakes stay small and recent.
- Spec 02 completed, and Phase 2 cut into 7 slices (ISS-020 … ISS-026). The learner writes S3 (Postgres search query) and S6 (eval metrics).
- Found: a local Postgres already uses port 5432, so our Docker database uses **5433**. A port is a numbered door; only one program can answer each.
- New glossary terms added *before* code: content hash, ingest, retriever, baseline, key fact, recall@5, MRR, migration, app role.

**Next session starts with:** S1 (Docker Postgres + migrations), once Docker Desktop is running; or S5 (golden set to 20) if it isn't.

---

## 2026-10-22 — Picking up: status check before S1

**Where we are:** Phase 2, step 3 done (spec complete, sliced into S1–S7, ISS-020 … ISS-026). No slice started yet. Docker Desktop is still not running. The repo is clean and in sync.

**What we learned (S1, the database):**
- **Why a database:** Phase 1 re-embedded all 23 chunks on every question. A database keeps chunks and vectors on disk: embed once, search many times.
- **Postgres + pgvector:** tables with fixed column types; `vector(1024)` stores an embedding, and the table itself rejects a 1,536-number vector.
- **Docker:** image = recipe, container = running box, volume = its disk, port 5433 = the door (5432 was taken).
- **Migrations:** numbered SQL scripts that Alembic applies in order and records in `alembic_version`; never edited once run.
- **Least privilege:** the app logs in as `rag_app`, which can read and write rows but can't drop tables (real result: `InsufficientPrivilege`) and isn't a superuser, so Phase 4's row-level security will apply to it.
- **HNSW index:** a neighbour map so search doesn't compare every row; it's approximate.

**How we learned it:** concept intro, then tests first (red: no `app.db`), then the build. 10/11 passed on the first run; the failure was in the test (a pgvector `Vector` has no `len()`, use `.dimensions()`). Then the real dev database was started and migrated, and we checked tables, columns, and roles with `psql`.

**What I can now explain:** pending (the S1 check questions in `lessons/02-databases-and-apis.md`).

**Still unclear / open questions:** none raised.

**Next session starts with:** S1 check questions, then S2 ingest (ISS-021): transactions, hashing, idempotency.

**Update — health check (2026-10-22):**
- All green: 45 offline, 11 db, and 2 live tests pass; lint clean; dev database healthy at `0001 (head)`; repo in sync.
- Fixed one risk: the image tag `pg16` floats (it can silently change), so it's pinned to `0.8.7-pg16`. Recreating the container kept the data, because it lives in the volume, not the container.
- Open: rotation of the OpenAI and Groq keys (exposed 2026-10-15) still unconfirmed; check questions for Concept 5 and S1 unanswered.

**Update — S2 ingest done (2026-10-22, ISS-021):**
- **Fingerprints:** a SHA-256 hash per file. Same fingerprint means skip: the 2nd real run took 0.7 s (the 1st took 9.6 s) and made **zero** Mistral calls.
- **Transactions:** update the document, delete its old chunks, and insert the new ones, all or nothing. Proven by a test where a wrong-size vector makes the insert fail and the old version survives.
- **Per-document transactions:** one bad file is reported (`failed`), and the other 10 still go in.
- **Idempotency:** run it as often as you like; same result, no cost.
- Embed *before* the transaction, so slow network calls don't hold database locks.
- Testing lesson: a test that *guessed* a number (org chart = 1 chunk) was wrong; measuring it in the test fixed it.
- Real database now: 11 documents, 23 chunks, 1,024 numbers each, from `mistral-embed`.

**Next session starts with:** S2 check questions, then **S3: you write the Postgres search query** (ISS-022).

**Update — S3 exercise set (2026-10-22, ISS-022):**
- Concepts taught on the real database: the SQL shape (SELECT, FROM, JOIN, WHERE, ORDER BY, LIMIT); `<=>` = cosine **distance** (0 = same) vs our **similarity** score (1 = same), where similarity = 1 − distance; `&&` = arrays share an element; order by the distance itself so the HNSW index can be used; parameters instead of pasted values.
- Exercise: write `_SEARCH_SQL` in `app/retrieval/pg_search.py` against 14 tests (`tests/test_pg_search.py`), with a five-blank scaffold in `lessons/02-databases-and-apis.md`.
- Checked the exercise is fair before handing it over: a correct query passes 14/14, and three typical mistakes (`ORDER BY score DESC`, forgetting `is_active`, returning distance as the score) are each caught. One test first failed for a correct query (Postgres chose the other index and sorted). The test was fixed to also forbid sorting.
- Plumbing: a `Retriever` protocol; `Answerer` accepts any retriever.

**Next session starts with:** fill the five blanks until `uv run pytest -m db tests/test_pg_search.py -v` shows 14 passed.

**Question asked — "why aren't we using a vector DB?" (2026-10-22):** we are: pgvector makes Postgres one. We chose not to add a *dedicated* vector DB (ADR-0001) because security needs vectors, documents, and permissions in one place, with one transaction and database-enforced isolation; pgvector is fast enough at our scale. The comparison was added to `lessons/02-databases-and-apis.md`.

---

## 2026-10-23 — Picking up: S3 exercise, blank by blank

**Where we are:** Phase 2. S1 (database) and S2 (ingest) are done. S3 (ISS-022) is in progress: `_SEARCH_SQL` is still empty, and the learner is filling it blank by blank in chat (⑤ and ② first). Docker Desktop is not running today. The repo is clean and in sync.

**What we learned:** nothing new yet. Yesterday ended with a worked example for blanks ⑤ and ②.

**How we learned it:** —

**What I can now explain:** pending (answers for blanks ⑤ and ②).

**Still unclear / open questions:** how to work through the exercise in chat. Answer: type each blank's answer as a message.

**Next session starts with:** answers for ⑤ and ②, then ①, ③, ④; paste the query into the file; run the 14 tests (start Docker first).

**Update (later on 2026-10-23): the query explained**
- The learner didn't know the blanks and asked for an explanation. Walked through the query in the order the database runs it: JOIN (match a chunk to its document by `document_id`), WHERE (same tenant, active, shares a role: the security part), ORDER BY distance `<=>` (closest first, so the HNSW index is used), LIMIT k, then SELECT with score = 1 − distance (real numbers: distance 0.150 → score 0.850).
- The full query was shown; the learner is to **type** it into `_SEARCH_SQL`.
- Check question asked: why are 0.850 (Phase 1) and 0.150 (`<=>`) both correct for the same chunk?

---

## 2026-10-26 — Picking up: type the query in

**Where we are:** Phase 2, S3 (ISS-022). The query was explained on 2026-10-23, but `_SEARCH_SQL` is still empty. Docker Desktop is not running. The repo is clean and in sync.

**What we learned:** nothing new yet. The session started with "where are we now".

**How we learned it:** —

**What I can now explain:** pending (check question: 0.850 vs 0.150).

**Still unclear / open questions:** none raised.

**Next session starts with:** type the query into `app/retrieval/pg_search.py`, start Docker, run `uv run pytest -m db tests/test_pg_search.py -v` (14 tests).

---

## 2026-10-28 — Question: what does production take?

**Where we are:** Phase 2, S3 (ISS-022): `_SEARCH_SQL` is still empty, waiting for the learner to type it in. The repo is clean and in sync.

**What we learned:**
- **Production** = it runs on a server you don't sit at, real people use it, and it keeps working, or **fails safely**, when nobody is watching.
- Three layers stand between us and production. (1) Finish the safety phases 3–7: better search, login and per-company isolation, guards, audit trail, eval gate. (2) Production prep, stages A–E: server and HTTPS, secrets, monitoring and alerts, CI/CD, load and failure tests, backups with a tested restore. (3) Running it: SLOs, on-call, key rotation, feedback loop.
- "Ready" is decided by **10 measurable gates** (G1–G10 in `docs/production-plan.md`), not by feel. Examples: 0 cross-tenant leaks, ≥ 95 % injection block rate, a restore drill passed in the last 30 days.
- Some production habits are already in place: secrets out of git, the non-superuser `rag_app`, versioned migrations, a pinned image, transactions, tests.

**How we learned it:** reviewed `docs/production-plan.md` against what's actually built.

**What I can now explain:** pending.

**Still unclear / open questions:** D-P3, the hosting budget (the < $20 covers AI only), is still undecided (ISS-016). It's not needed until after Phase 7.

**Next session starts with:** type the S3 query into `app/retrieval/pg_search.py` and run the 14 tests.

---

## 2026-10-29 — Picking up: status check

**Where we are:** Phase 2, S3 (ISS-022): `_SEARCH_SQL` is still empty (unchanged since 2026-10-22). Docker Desktop is not running. The repo is clean and in sync.

**What we learned (system map):** the learner asked for concepts only: what happens, and where.
- **Four places:** Python on the Mac (our logic), the Docker database on the Mac (chunks and vectors), Mistral's servers (text → 1,024 numbers), and Groq's servers (the LLM writes the answer).
- **What leaves the machine:** document text goes to Mistral at ingest; the question goes to Mistral, and the question plus 5 chunks go to Groq, on every question. That's a privacy decision for real data (D-P6).
- **Journey A (ingest, A1–A5)** and **Journey B (question, B1–B7)**, each step with its concept, file, place, and a real example.
- **The gap S3 closes:** the database is filled, but questions still search an in-memory copy that re-embeds all 23 chunks per question. With the S3 query, only 1 text (the question) is embedded.

**How we learned it:** a concept map, saved as `lessons/system-map.md`.

**What I can now explain:** pending (two check questions in the map).

**Still unclear / open questions:** whether the learner still wants to write core code (the S3 query), or prefers the assistant to write it and the learner to explain it back. Asked.

**Next session starts with:** the learner's choice on S3, then continue.

**Update — S3 done: answers now come from the database (2026-10-29, ISS-022):**
- The learner asked to get moving, so we went with Option A: the assistant wrote the query and the learner explains it back.
- 14/14 search tests pass, including security (another company's, inactive, and wrong-role chunks are never returned) and use of the HNSW index.
- Connected to the app: the CLI answers from Postgres when `DATABASE_URL` is set.
- Real comparison, same question: **identical top-5 scores** (0.850 …), **1 text to Mistral instead of 24**, **3.2 s instead of 5.1 s**. "CEO's salary" → "I don't know" (best 0.692).
- Lesson: the database pays off because the expensive work (embedding the chunks) happens once at ingest, not on every question.

**What I can now explain:** pending (three explain-back questions in `lessons/02-databases-and-apis.md`, S3 result).

**Next session starts with:** the three explain-back questions, then S4: the web API (`POST /v1/ask`).

**Update — pace changed; S4 web API done (2026-10-29, ISS-023, ISS-027):**
- The learner said the project is getting delayed: **build now, study later**. From here, the assistant builds each slice end to end with a short intro; the depth goes into `lessons/02-databases-and-apis.md` for later study.
- S4 built: `POST /v1/ask`, `GET /healthz`. Real curl runs: 200 with answer and citation, 200 "no_answer", 422 for an empty question, 503 with the database stopped. 0 question words in the server log; it listens on 127.0.0.1 only.
- **A real bug found by breaking things on purpose:** after a database restart, `/healthz` said OK but `/v1/ask` failed forever, because it held a dead start-up connection. Fixed with a connection pool that checks each connection before use. Regression test added; real recovery confirmed.
- Lessons (to study): status codes 200/422/503; never leak internal errors; a health check must test the same path users use.

**Still unclear / open questions:** explain-back questions for S3 and S4 (pending, for later study).

**Next session starts with:** S5, golden set to 20 questions with key facts (ISS-024).

**Update — "it's not starting" (2026-10-29, ISS-028):**
- On the assistant's machine the server started fine. Reproduced the two likely causes: with the database down, the server retried forever with `connection refused` and no hint; from the wrong folder, `Failed to spawn: uvicorn`.
- Fixed the first: start-up now fails within about 5 s with "Cannot reach the database … Is Docker running? … docker compose up -d".
- Added a start-up checklist and a "you see / meaning / fix" table to the S4 notes. Note: a running server keeps the terminal busy on purpose.
- Lesson: an error message should say **what to do**, not just what broke.
- **The learner started the API themselves:** Docker Desktop showed `db-1` running on 5433, and `uv run uvicorn app.main:app` printed `Uvicorn running on http://127.0.0.1:8000`. Opening `/` gave `404 Not Found`, which is correct because there's no front page; the questions page is `/docs`. Learned: the database port (5433) and the web API port (8000) are different programs; 404 = "no such address here".

**Update — S5 golden set done (2026-10-29, ISS-024):**
- 20 test questions (14 answerable, including 4 two-document; 6 unanswerable, including 4 near-misses), each answerable one with **key facts**.
- **Testing the tests:** a checker proves every key fact is on its source page, so a typo can't make a right answer look wrong.
- Real preview of the 10 new questions: 9/10 correct. g17 is the org-chart retrieval miss again, which strengthens ISS-017 for Phase 3.
- Seen in real answers: narrow spaces (`5\u202fmph`), non-breaking hyphens, and `**bold**`. S6's matching must normalise them.

**Next session starts with:** S6, eval metrics (recall@5, MRR, key-fact score, No-Answer accuracy, latency).

**Update — S6 metrics done (2026-10-29, ISS-025):**
- `eval/metrics.py`, written by the assistant (build now, study later): **recall@5** (is the right page in the top 5?), **MRR** (how high?), **key-fact score** (share of facts in the answer, after normalising real output), **No-Answer accuracy + false refusals** (refuse exactly when right), **p50/p95 latency** (typical vs slow-but-normal).
- 22 tests with hand-worked numbers and real model replies; the golden checker now reuses the same `normalise`.
- Known limit: key facts are substring matches (`£4200` ≠ `£4,200`); an AI judge comes in Phase 7.

**Next session starts with:** S7, run the 20 questions through the API, save the baseline, release `v0.2.0`.

---

## 2026-10-30 — S7 baseline, and a study companion for a second chat

**Where we are:** Phase 2, S7 (ISS-026): the eval runner, the baseline, then `v0.2.0`. S1–S6 are done.

**What we learned:**
- **Baseline** = the scores of a fixed, committed version; every later change must be compared against it.
- Phase 2 baseline (real models, 20 questions): recall@5 **0.929**, MRR **0.917**, key facts **0.857**, answered **12/14**, No-Answer **6/6**, 0 errors.
- Both failures (g06, g17) are **retrieval** failures (the org chart isn't found), and that's Phase 3's target.
- Latency p50/p95 9.5/13.3 s is inflated: the first 6 questions took ~1.4 s, then Groq's free tier throttled the burst (ISS-029). Numbers need their context.
- Phase 2 closed: released **`v0.2.0`**.

**How we learned it:** wrote `lessons/study-companion-context.md`, a context pack to paste into another chat. It holds tutor instructions (concepts first, one question at a time, don't change the repo, never print `.env`), project state, the system map, real numbers, incidents, a 10-item study agenda, and files to open.

**What I can now explain:** pending. The second chat ends each session with a summary to paste back here.

**Still unclear / open questions:** the study agenda items, which the second chat now covers.

**Next session starts with:** Phase 3 kickoff (better retrieval: keyword + vector search, reranking), aiming to fix g06/g17 without losing anything else. The study chat works through the agenda in parallel.

## 2026-10-31 — Codebase walkthrough before Phase 3

**Where we are:** Phase 2 is released (`v0.2.0`); Phase 3 (better retrieval) has not started. Offline tests: 90 pass, ruff clean.

**What we learned:**
- The whole request path today is one straight line: question → embed it → one SQL query (tenant + active + role filter, closest by cosine) → top 5 chunks → LLM with the `answer_v1` prompt → parse citations → either an answer with valid citations, or the No-Answer.
- The answerer only knows the `Retriever` interface (`search(question, k)`), so Phase 3 can replace *how* chunks are found without touching how answers are checked.
- g06 and g17 are both two-hop questions: the first document names a role ("Head of Procurement"), and only the org chart has that person's email. The org chart doesn't sound like the question, so vector search alone misses it.

**How we learned it:** read `plan.md`, the trackers, `docs/architecture.md` §11 (invariants), and the code in `app/answering`, `app/retrieval`, `app/main.py`, the migration; ran the offline tests.

**What I can now explain:** pending.

**Still unclear / open questions:** none new.

**Next session starts with:** Phase 3 kickoff: agree decisions and write spec 03 (keyword search + RRF, reranker, LangGraph, three-way eval).

---

## 2026-10-31 — Phase 3 kickoff: why the org chart is missed

**Where we are:** Phase 3 (better retrieval + LangGraph). Spec 03 written; slices S1–S4 (ISS-030 … ISS-033).

**What we learned:**
- **Diagnose before fixing:** the "missing" pages aren't far away. In dense search, g06's org chart ranks **6th** and g17's handbook **7th**, just below the top-5 cut.
- So the plan: cast a **wider net** (20 candidates from meaning search + keyword search, combined with **RRF**), then let a **reranker** (a model that reads question and chunk *together*) choose the best 5, and say "I don't know" early when even the best is irrelevant.
- New glossary terms before code: keyword search, hybrid search, RRF, reranker, relevance threshold.

**How we learned it:** measured the dense rank of every expected page for the two failing questions.

**What I can now explain:** pending (study chat).

**Update — S1 keyword + hybrid search (ISS-030):**
- **Keyword search** (Postgres full text): finds chunks containing the question's exact words; great for names like SwiftParts or SafeSite.
- **RRF** merges ranked lists by **rank** (1 / (60 + rank), summed), because keyword scores and similarities aren't on the same scale.
- Real result, mixed: g17's handbook went **7th → 1st** ("gift", "declare" match exactly), but the org chart went **down** (g06 6th → 10th). It's a **two-hop** page: the question asks "who owns the contract", the contract says "Head of Procurement", and only the org chart names her. The question's words don't describe that page.
- Lesson: a technique that's "usually better" can hurt specific cases. Measure per question, not only on average.

**Next session starts with:** S2, the reranker.
