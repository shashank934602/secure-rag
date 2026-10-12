# Development Workflow

Spec-driven and incremental. The context files say what to build and where we are; the skills below say how to get from idea to merged code. Don't invent behaviour that isn't in a spec.

## The loop for each build phase

| Step | Skill | Output |
|------|-------|--------|
| 1. Align | `/grill-with-docs` | Resolved questions; new terms in `GLOSSARY.md`; ADRs for hard-to-reverse decisions |
| 2. Spec | `/to-spec` | `context/feature-specs/NN-slug.md` in the format below |
| 3. Slice | `/to-tickets` | Vertical-slice tickets with blocking edges, each logged as an `ISS-NNN` task in `issue-tracker.md` |
| 4. Build | `/implement` (drives `/tdd` at the agreed seams) | Code + tests, one slice at a time |
| 5. Review | `/code-review` | Standards review + spec-conformance review |
| 6. Ship | `/pr` | PR body with evidence (eval numbers for anything touching retrieval, guards, or prompts); `CHANGELOG.md` entry; issues closed |
| 7. Reflect | `/retro` | Improvements to these context files and tooling |

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
