# Development Workflow

Spec-driven, incremental, and **teaching-first**. The context files say what to build and where we are; the skills below say how to get from idea to merged code. Don't invent behaviour that isn't in a spec.

## Teaching-first (this is a learning project — `plan.md` §0)

- **Nothing is built blindly.** Before any step: say what we're about to do, why, and which idea it teaches. After it: show what changed and check understanding.
- **Every phase:** (1) **Lesson** — the phase's ideas in plain language, with a runnable experiment where possible, saved in `lessons/NN-….md`, ending with 2–3 questions; (2) **Build** — tests are provided first; the learner writes the **core** code (retrieval, guards, audit chain, eval metrics) until they pass; the agent writes plumbing (Docker, config, DB setup, wiring) and explains it; (3) **Walkthrough + quiz + one experiment** (change one thing, measure the effect).
- **Done** = the phase's checks pass **and** the learner can explain every part they wrote.
- Prefer small steps the learner can follow over large changes; when the agent must write a lot, walk through it afterwards.

## The loop for each build phase

| Step | Skill | Output |
|------|-------|--------|
| 0. Learn | lesson in `lessons/` | The phase's ideas explained, with an experiment and questions |
| 1. Align | `grilling` | Resolved questions; new terms in `GLOSSARY.md`; ADRs for hard-to-reverse decisions |
| 2. Spec | `/to-spec` | `context/feature-specs/NN-slug.md` in the format below |
| 3. Slice | `/to-tickets` | Vertical-slice tickets with blocking edges, each logged as an `ISS-NNN` task in `issue-tracker.md` |
| 4. Build | `tdd` at the agreed seams | Tests provided first; learner writes core code, agent writes plumbing; one slice at a time |
| 5. Review | `/code-review` | Standards review + spec-conformance review |
| 6. Ship | `/pr` | PR body with evidence (eval numbers for anything touching retrieval, guards, or prompts); `CHANGELOG.md` entry; issues closed |
| 7. Reflect | walkthrough + quiz + experiment | Learner can explain every part; improvements to these context files |

Use as needed:

| Situation | Skill |
|-----------|-------|
| Learning a concept before building it (RRF, HNSW, RLS, RAGAS…) | `/teach` |
| Choosing between tools or models with evidence (injection classifiers, rerankers, benchmarks) | `research` |
| Answering a design question with a throwaway experiment (chunk sizes, hybrid vs dense) | `prototype` |
| Designing a module interface (guards, retriever, audit trail) | `codebase-design` |
| Retrieval returns wrong chunks, a guard misfires, eval regresses | `diagnosing-bugs` |
| Ending a session mid-phase | `/handoff` |
| An agent reply didn't make sense | `/wait-what` |

## Seams for `/tdd`

Agree these before writing tests; test only here.

| Seam | Interface | Catches |
|------|-----------|---------|
| Ingestion | `ingest(document_id) -> IngestResult` | Chunking, quarantine, idempotent re-ingest, ACL copied to chunks |
| Retrieval | `search(user, query) -> list[Chunk]` | ACL + RLS filtering, inactive chunks excluded, hybrid fusion |
| Each guard | `check(input, user) -> GuardVerdict` | Block/allow/mask decisions, fail-closed on errors |
| Answering | `answer(user, question) -> AnswerResult` | Full graph with fake LLM: refusal, No-Answer, retry, citations |
| Audit trail | `append(event)`, `verify(tenant) -> VerifyResult` | Hash chain, append-only, tenant scoping |

## Feature spec format

`context/feature-specs/NN-slug.md`:

- **Goal** — one paragraph.
- **Implementation** — numbered steps.
- **Scope limits** — what this unit must *not* touch.
- **Check when done** — verifiable statements, including eval numbers where relevant.

## Scoping rules

- One phase or subsystem at a time; small, verifiable increments.
- Split a unit if it combines: a schema migration *and* new API behaviour; guard changes *and* retrieval changes; prompt changes *and* model changes (you can't tell which moved the eval).
- If a unit can't be verified end to end quickly, it's too big — split it.

## Handling missing requirements

- Ambiguous → resolve it in the relevant context file (or with `/grill-with-docs`) before implementing.
- Missing → open a `question` issue in `issue-tracker.md` before continuing.
- Found a bug or shortcut you can't fix now → open a `bug` or `debt` issue; don't leave TODOs untracked.

## Before moving to the next unit

1. The unit works end to end within its scope and its "Check when done" list passes.
2. No invariant in `docs/architecture.md` §11 is violated.
3. The eval harness (from Phase 2 on) shows no regression, or the regression is explained.
4. `progress-tracker.md` reflects what was actually built.
5. `CHANGELOG.md` has an entry under **Unreleased**, and the unit's issues are closed with a resolution.
