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
