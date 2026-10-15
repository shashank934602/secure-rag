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
