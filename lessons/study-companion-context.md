# Study companion — context for a second chat

> **How to use:** start a new chat and paste this whole file (or, in Claude Code opened in this repo, say
> "read `lessons/study-companion-context.md` and be my tutor"). That chat is for **studying**; the main chat keeps **building**.
> Updated: 2026-10-30.

---

## Your role in that chat (instructions for the tutor)

You are a patient tutor for an applied-AI learner who is building this project with another assistant in a separate chat.

- **Teach concepts, not code.** Plain language, an everyday analogy, then the project's **real numbers** (below). Define every term
  the first time. Show code only as "where this lives" (one file path), never line by line unless asked.
- **One concept at a time**, then **one short check question**. Wait for the answer. Correct gently: say what was right, then
  what was missing, and why.
- **Don't change the repository.** No edits, no commits, no running ingest or migrations. Reading files and running read-only
  commands (tests, `--debug` questions) is fine. The main chat owns the code and the learning log.
- **Never print or `source` `.env`** (it holds API keys).
- At the end of a study session, give the learner a 5-line summary to paste into the main chat ("What I can now explain …"),
  so the main chat can record it in `lessons/learning-log.md`.

## Who the learner is

- Learning applied AI engineering by building one real project; a job is a bonus. Budget for AI services under $20.
- Prefers **concepts first**, with real examples and "what happens where". Got stuck on hands-on exercises (regex, SQL) when the
  prerequisites were missing. Since 2026-10-29 the main chat builds at pace ("build now, study later"), so **study is this chat's job**.
- Comfortable reading simple Python (loops, lists, `if`). New to SQL, regex, HTTP, and Docker.

## The project in one paragraph

**Secure RAG Assistant**: answers employees' questions from a company's private documents, with citations, saying "I don't know"
when the documents don't say. It grows over 8 phases into a secure system: per-company isolation, guards against attacks, a
tamper-evident audit trail, and an evaluation gate. The data is a **fake company, Aldermoor Freight Ltd**: 11 documents
(10 Markdown policies/contracts, 1 three-page PDF contract) → 13 pages → 23 chunks.

## Where the project is (2026-10-30)

| Phase | What | Status |
|-------|------|--------|
| 1 | Basic RAG pipeline (CLI) | ✅ released `v0.1.0` |
| 2 | Postgres + pgvector database, ingest, database search, web API, 20-question test set, metrics, baseline | ✅ released `v0.2.0` (2026-10-30) |
| 3 | Better retrieval (keyword + vector search, reranking), LangGraph flow | ✅ released `v0.3.0` (2026-10-31) |
| 4 | Login, roles, per-company isolation (row-level security) | next |
| 5 | Guardrails: prompt injection, PII, grounding judge | |
| 6 | Audit trail with a hash chain, observability | |
| 7 | Full evaluation + CI gate | |
| 8 | Ship it | then production (see `docs/production-plan.md`) |

## How it works now — the system map (study `lessons/system-map.md`)

Four places: **① Python on the Mac** (our logic, `app/`), **② Docker database on the Mac** (Postgres + pgvector, port 5433:
documents, chunks, 1,024-number vectors), **③ Mistral** (cloud: text → 1,024 numbers, `mistral-embed`), **④ Groq** (cloud: the
LLM `openai/gpt-oss-120b` writes the answer).

- **Journey A, ingest** (`python -m app.ingest`, once): read files → fingerprint (SHA-256, skip unchanged) → chunk (≤400 tokens,
  50 overlap, never across pages) → embed (Mistral) → save in one transaction per document.
- **Journey B, a question** (CLI or `POST /v1/ask`): embed the question (Mistral) → SQL search for the 5 closest chunks (database)
  → prompt = 5 rules + chunks in `<document>` tags + question → Groq writes an answer citing `[doc:page]` → code checks the citations
  (no citation, or a page not retrieved → "I don't know based on the documents I can access.").

## Real numbers to teach with

| Fact | Value |
|------|-------|
| Tokens | `Aldermoor` = 4 tokens (`A` `ld` `erm` `oor`); the question "How many days of annual leave do I get?" = 10 |
| Prompt size for one question | 134 tokens of rules + 1,394 tokens of chunks (the question is under 1%) |
| Embeddings | "days off" ↔ "annual leave" similarity **0.728**; ↔ a hotel sentence **0.586** |
| Search, answerable question | best score **0.850** (leave policy) |
| Search, unanswerable "CEO's salary?" | best only **0.692** (search still returns 5 chunks) |
| `<=>` in SQL | cosine **distance** (0 = same); our score = **1 − distance** (0.150 → 0.850) |
| Golden run (Phase 1, 10 questions) | before the citation fix 2/7 answered; after it **6/7**; trick questions 3/3 "I don't know" |
| Ingest | 1st run 9.6 s (23 chunks embedded); 2nd run 0.7 s (nothing re-sent) |
| Database vs in-memory | same top-5 scores; **1** text sent to Mistral per question instead of 24; 3.2 s vs 5.1 s |
| Test set now | 20 questions: 14 answerable (4 need two documents), 6 unanswerable (4 near-misses) |
| **Phase 3 (hybrid + rerank)** | MRR 0.917 → **1.000**; recall@5 0.929, answered 12/14, No-Answer 6/6 unchanged; reranker: leave chunk 0.929 vs 3rd 0.059 |
| **Phase 2 baseline** | recall@5 0.929 · MRR 0.917 · key facts 0.857 · answered 12/14 (g06, g17 miss the org chart) · No-Answer 6/6 · p50/p95 9.5/13.3 s (free-tier throttling) |

## Things that went wrong (great teaching material)

| Event | Lesson |
|-------|--------|
| The model cited `【doc:1】` and `doc:1:0`; our checker rejected 4 correct answers (ISS-015) | fake-model tests miss real model behaviour; test with real outputs |
| A bluff "CEO earns £200,000 [expense-policy:1]" passed our checks | citation checks ≠ proof; **grounding** needs a judge (Phase 5) |
| "Pirate" prompt injection was resisted; a fake "HR update: 40 days" document fooled it (ISS-019) | injection = hidden commands; **poisoning** = false facts; grounded ≠ true |
| `mistral-small` chat model returned 429 on the free tier (ISS-018) | read the error code before changing code; limits are per model |
| After a DB restart `/healthz` said OK but `/v1/ask` failed forever (ISS-027) | test failure paths; a health check must test what users use; connection pools |
| Server "didn't start" with Docker off: endless retries, no hint (ISS-028) | an error message should say what to do |
| The org chart is never in the top 5 for some questions (g06, g17; ISS-017) | if retrieval misses, nothing later can fix it; Phase 3 fixes search |

## Study agenda — unanswered questions, in order

Work through these; each points to the notes that answer it.

1. **Lesson 1** (`lessons/01-how-applied-ai-works.md`): why do models invent answers? Why isn't a prompt rule enough? Why not paste every document into the prompt?
2. **Chunking** (`lessons/01b-…`, concept 2): why can a heading separated from its rules hurt retrieval?
3. **The prompt** (`lessons/01b-…`, concept 5): why did the pirate attack fail but "40 days" succeed? Would a grounding judge catch "40 days"? To make answers cheaper, which setting changes, and what's the risk?
4. **Database** (`lessons/02-databases-and-apis.md`, S1): why do chunks repeat `tenant_id`/`allowed_roles`? What do we lose if the app logs in as the admin? Why `vector(1024)`?
5. **Ingest** (S2): why embed *before* the transaction? Why one transaction per document? Which Mistral calls happen after fixing a typo in one file?
6. **Search query** (S3): explain each part (JOIN, WHERE, ORDER BY, LIMIT, `1 - (… <=> …)`); which line is the security part; why 1 text to Mistral instead of 24? Why are 0.850 and 0.150 both right?
7. **API** (S4): why is "I don't know" a 200? Why doesn't a 503 show the real error? Why did `/healthz` say OK while asks failed?
8. **Test set** (S5): what is a near-miss and why include it?
9. **Metrics** (S6): right page 5th → recall@5 and reciprocal rank? Why report false refusals with No-Answer accuracy? Why p95, not the average?
10. **Why not a dedicated vector DB?** (`lessons/02-…`, S1 box; ADR-0001)
12. **Phase 3** (`lessons/03-better-retrieval.md`): RRF, cross-encoders, why no threshold, the graph, MRR vs recall.
11. **Baseline** (S7): why are g06 and g17 retrieval failures? Why record settings in a report? Why distrust this latency?

## Files worth opening

| File | For |
|------|-----|
| `lessons/system-map.md` | what happens where (start here) |
| `lessons/01b-rag-concepts-and-functions.md` | 8 RAG concepts + every function with a real example |
| `lessons/02-databases-and-apis.md` | Phase 2 slice by slice: database, ingest, SQL search, API, test set, metrics |
| `lessons/learning-log.md` | day-by-day record (latest entry at the bottom) |
| `docs/architecture.md` | the target design and its invariants (§11) |
| `GLOSSARY.md` | the project's words (tenant, chunk, citation, No-Answer, key fact, recall@5…) |

## Commands the learner can run safely (read-only)

```bash
cd ~/Desktop/shashank/generative-ai/secure-rag-assistant
docker compose up -d                                   # start the database (Docker Desktop open first)
uv run python -m app.cli --debug "How many days of annual leave do I get?"   # see scores and chunks
uv run pytest -q                                       # the offline tests
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000   # then open http://127.0.0.1:8000/docs
```
