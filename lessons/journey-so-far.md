# The journey so far: what we built and what we learned

> A one-page map of the project from 2026-10-12 to 2026-11-06. Every number is real and comes from the changelog,
> the lessons, or a live run. For depth, follow the lesson links; for the day-by-day story, see `learning-log.md`.

## What the project is, in one paragraph

A **Secure RAG Assistant**: employees ask questions in plain English and get answers *from their own company's
documents*, with citations, or an honest "I don't know". It is built for companies that can't afford mistakes, so it
also has to prove three things: **no one sees what they shouldn't** (not another company's data, not HR-only pages),
**attacks are stopped** (people trying to trick the AI), and **every answer can be explained later** (a tamper-evident
record). RAG stands for *Retrieval-Augmented Generation*: find the right pages first, then let the AI write an answer
using only those pages.

## The timeline

| Version | Date | Phase | What it added, in one line |
|---|---|---|---|
| — | 10-12 → 10-16 | 0 · Setup | Accounts, tools, plan, rules for how we work |
| `v0.1.0` | 10-19 | 1 · Basic RAG | Read documents → cut into chunks → find the right ones → answer with citations |
| `v0.2.0` | 10-30 | 2 · Database + API | Postgres stores everything; a web API answers; the first measured baseline |
| `v0.3.0` | 10-31 | 3 · Better search | Keyword + meaning search combined, a reranker, the flow as a graph |
| `v0.4.0` | 11-02 | 4 · Access control | Logins, companies kept apart *by the database itself*, role-based documents |
| `v0.5.0` | 11-02 | 5 · Guardrails | Attack detection, poisoned-page removal, private-data masking, a fact-checking judge |
| `v0.6.0` | 11-03 | 6 · Audit trail | Every answer recorded and explainable; edits to the record are detectable |
| `v0.7.0` | 11-03 | 7 · Eval gate | Hundreds of test cases; CI refuses any change that makes security worse |
| `v0.8.0` | 11-04 | 8 · Ship it | One command starts everything; a web page; a README a stranger can follow |
| `v0.9.0` | 11-05 | Production Stage B | Secret scanning, rate limits, token budget, stronger logins |
| — | 11-06 | Demo | Ran the whole flow live in a browser |

Every release from Phase 5 on was attacked by an **independent tester** before it shipped, and every release had real
bugs found and fixed because of it.

---

## Phase by phase: what we built, and the idea behind it

### Lesson 1 · How applied AI works ([01](01-how-applied-ai-works.md), [01b](01b-rag-concepts-and-functions.md))
- A language model **predicts the next piece of text**; it doesn't look things up. That's why it *hallucinates*
  (invents confident answers) about things it was never shown, like your company's leave policy.
- **Tokens:** models read text in pieces of about ¾ of a word, and providers charge per token.
- **Embeddings:** text turned into a list of numbers, so "holiday" and "annual leave" end up close together.
- **Prompt injection:** text that tries to give the AI new orders ("ignore your rules…"). The central threat of this project.

### Phase 1 · The basic pipeline (`v0.1.0`)
- A fake company, **Aldermoor Freight**: 10 documents and a 3-page PDF, cut into **23 chunks** of about 400 tokens
  with 50 tokens of overlap, so a sentence cut at a boundary still appears whole in one chunk.
- Flow: question → embed it → find the closest chunks → give them to the model with "answer only from these, cite them".
- Result: 6/7 answerable questions answered, and 3/3 unanswerable ones correctly got "I don't know".
- **Learned:** the AI provider was swapped (Groq → Mistral) by changing config only. Designing parts to be swappable pays off later.

### Phase 2 · A real database and an API (`v0.2.0`) ([02](02-databases-and-apis.md))
- **Postgres + pgvector:** one database for documents, chunks and their embeddings (ADR-0001: one store, not two).
- **Ingest is safe to re-run:** each document has a fingerprint (a hash), so unchanged files are skipped and a failed
  file is rolled back instead of half-saved.
- **Least privilege:** the app connects as a limited database user (`rag_app`), never as the admin.
- **The first baseline**, 20 test questions: recall@5 **0.929**, MRR **0.917**, key facts **0.857**, 6/6 "I don't know" correct.
- **Learned:** *you can't improve what you haven't measured*. The baseline is what every later change is compared to.

### Phase 3 · Better search (`v0.3.0`) ([03](03-better-retrieval.md))
- **Hybrid search:** meaning-based search finds "holiday" for "annual leave"; keyword search finds exact codes and
  names. The two result lists are merged with *Reciprocal Rank Fusion* (a simple way to combine rankings).
- **Reranker:** a second, more careful local model rescores the top 20 and keeps the best 5.
- **LangGraph:** the answering steps became a *state machine* (a flowchart in code), so retries and early exits are explicit.
- Result: MRR **0.917 → 1.000** (the right page is now always ranked first), and nothing got worse.
- **Learned:** some questions need two pages joined together (the org chart). Better search doesn't fix that; it's a known limit (ISS-017).

### Phase 4 · Who can see what (`v0.4.0`) ([04](04-access-control.md))
- **Row-level security (RLS):** the database itself hides other companies' rows, even if our code forgets a filter.
- **Roles on documents:** HR-only pages are filtered *inside the search*, so they never reach the AI.
- **Access tokens:** a signed login pass with ids only; roles are read from the database on every request.
- A second company, **Northgate Haulage**, with planted "canary" documents to detect leaks.
- Result: leakage check **0 leaks in 9 probes**, with 2/2 positive controls (proving the check *can* catch a leak).
- **Learned:** *make leaks impossible, not unlikely.* A wall in the database beats a filter someone could forget.

### Phase 5 · Guardrails (`v0.5.0`) ([05](05-guardrails.md))
- **Input guard:** pattern rules + a local classifier model refuse attacks before any search or AI call.
- **Context guard:** drops document chunks that contain hidden instructions; masks bank details, NI numbers and similar
  for users without permission (ADR-0004).
- **Output checks:** strip links, images and HTML (so an answer can't leak data to a website); check every citation is real.
- **Grounding judge:** a *different* AI model checks every claim is supported by the pages.
- **Fail closed:** if any guard breaks, the request is refused, never let through.
- Result: **45/50 attacks blocked, 3/50 normal questions wrongly refused**. Role-play attacks are the weak spot (ISS-048).
- **Learned:** *defence in depth.* Every layer assumes the one before it can fail. The AI guards are signals; the walls
  that truly hold are structural: RLS, the AI having no tools, and stripping links.

### Phase 6 · The audit trail (`v0.6.0`) ([06](06-audit-trail.md))
- Every request is recorded: who asked, a **keyed fingerprint** of the question (never the raw text), which pages were
  used, every guard decision, timings, the outcome.
- **Hash chain:** each record contains a fingerprint of the one before it, so editing or deleting an old record breaks
  the chain, and `/v1/audit/verify` finds it.
- Auditors can open any answer and see *why* the system said it.
- Loading the AI models at start-up made the first request after a restart go from 14.8 s to 3.8 s.
- **Learned:** in regulated work, "why did it say that?" must be answerable weeks later, with proof the record wasn't altered.

### Phase 7 · The eval gate (`v0.7.0`) ([07](07-eval-gate.md))
- Much bigger test sets: **320 attacks, 339 normal questions, 109 poisoned document passages**, a public set reported
  separately, and 28 real chunks that must *not* be flagged.
- Every number comes with an **error bar** (a 95% confidence interval).
- **The gate:** on every push, CI compares against the saved baseline and **fails** if security gets worse, a guard is
  switched off, a test case disappears, or a pinned model version changes (ADR-0006, the "ratchet": the bar can only rise).
- Baseline on the bigger set: **73.7% of attacks blocked** (67.7–79.0%), 6.9% false refusals. This is lower than Phase 5's
  45/50 because the test is now much larger and harder. That is the honest number.
- Proved it works: a deliberately weakened branch was **blocked by CI**.
- **Learned:** "it seems better" isn't engineering; a number with an error bar, checked automatically, is. Also: free
  tiers run out (Groq's daily token cap, Mistral's 429s), and **a report from an incomplete run must never become a baseline**.

### Phase 8 · Ship it (`v0.8.0`) ([08](08-ship-it.md))
- One Docker image (runs as a non-root user) and `docker compose up -d --wait`: database → migrations → demo data → API.
- `scripts/make_env.py` generates every local secret, so nobody copies passwords around.
- A small web page with a strict security policy; answers shown as plain text, so an answer can't inject code.
- Result: **fresh clone to first answer in 6.5 minutes**; all five README demos verified live.
- **Learned:** good work that nobody can run looks unfinished.

### Production Stage B · Hardening (`v0.9.0`) ([09](09-production-hardening.md))
- **Secret scanning** of the whole git history on every push. Testing it like a real mistake showed it **missed a Groq
  key**, so we added our own rules.
- **Dependency and image scans:** 34 known holes fixed (worst in the PDF reader, which reads untrusted files); 0 high or critical left.
- **Rate limits:** 20 questions/min per user, 120 per company; **token budget:** 200,000 per company per day, booked
  *before* any AI call. If Redis (the counter store) is down: refuse (503).
- **Stronger logins:** RS256 tokens (private key signs, public key checks), 15 minutes, key ids for rotation; 31 forgery
  attempts, all refused.
- **Separate fingerprint key per company**, so the same question can't link two companies.
- **Learned:** a *check* and an *update* done as two steps can be raced (8 simultaneous questions all slipped under the
  budget). The fix is to make them one atomic step, not to check harder.

### 2026-11-06 · Seeing it run
- Ran the README demo live in a browser: alice gets 25 days of leave; she gets "I don't know" for HR salary bands
  while harriet (HR) gets Band C; ned (the other company) gets *his* company's 28 days; an attack is refused in 0.0 s;
  a token with one letter changed gets 401.
- Learned why **Vercel doesn't fit**: it runs short-lived functions, while our API keeps two AI models loaded in memory
  and ships as one Docker image. Platforms that run Docker images (Render, Railway, Fly.io) fit as they are.
- Found **ISS-077**: the page shows the AI's `**bold**` marks raw.

---

## The big ideas, across the whole project

1. **Retrieve first, then generate.** The AI only knows what you hand it. Most quality problems are search problems.
2. **Make leaks impossible, not unlikely.** Put the rule where it can't be forgotten: in the database (RLS), not in a `WHERE` someone might skip.
3. **Defence in depth.** Several independent layers; AI-based guards are signals, structural walls are what hold.
4. **Fail closed.** When a guard, the judge or the limiter breaks, refuse. An open failure is silent; a closed one gets noticed.
5. **Measure with error bars, and let CI enforce it.** A baseline, a ratchet, and a gate that blocks regressions automatically.
6. **Test your tools against your own failure.** The secret scanner looked fine until it was fed a real Groq key.
7. **Atomic beats careful.** If two steps can be raced, someone will race them; make them one step.
8. **Store nothing raw.** Questions are kept as keyed fingerprints and redacted text, never as the original.
9. **An independent tester finds what the builder can't.** Every release had real bugs found by someone attacking it.
10. **Process slips are real bugs too.** A pipe once hid a failing test's exit code and a broken commit went out; now
    every suite's exit status is checked before committing.

## Key decisions (ADRs, the ones not to reverse silently)

| ADR | Decision |
|---|---|
| 0001 | Postgres is the single store (documents, vectors, audit) |
| 0002 | Access rules live on each chunk, enforced with row-level security |
| 0003 | No streaming: the whole answer is checked before anything is shown |
| 0004 | Private data is masked when a question is asked, based on who is asking |
| 0005 | Mistral for embeddings |
| 0006 | The eval gate is a ratchet: the bar only goes up |

## Where we are now, and what's next

- **Built:** all 8 phases and production Stage B. CI green on 5 jobs. Latest release `v0.9.0`.
- **Waiting on you:**
  - **ISS-075:** Stage A decisions (who the users are, hosting, budget, domain, region). Next step: compare Render, Railway and Fly.io.
  - **ISS-063:** GitHub settings (secrets, required checks, code owners).
  - **ISS-069:** record the demo video.
  - Rotate the API keys that leaked on 2026-10-15.
- **Known weak spots:** role-play attacks (ISS-048), two-page questions (ISS-017), anonymous floods need per-IP limits at
  the proxy (ISS-076), raw markdown on the page (ISS-077).
- **Study backlog:** the "Explain it back" questions at the end of Lessons 1b–9.
