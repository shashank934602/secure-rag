# Secure RAG Assistant — Agent Instructions

RAG over private documents with security guardrails, a tamper-evident audit trail, and an evaluation gate.
This file is the entry point for any coding agent working in this repo.

## Read before implementing or making an architectural decision

1. `plan.md` — roadmap: phases, why, what we need
2. `context/project-overview.md` — goals, scope, what is out of scope
3. `docs/architecture.md` — HLD, data model, guardrails, and the **Invariants** (§11)
4. `GLOSSARY.md` — domain language; use these terms in code, tests, and specs
5. `docs/adr/` — decisions that must not be silently reversed
6. `context/code-standards.md` — implementation rules
7. `context/ai-workflow-rules.md` — how work is scoped, specced, built, and reviewed
8. `context/progress-tracker.md` — current phase and what is actually built
9. `context/issue-tracker.md` — open bugs, tasks, and questions
10. `CHANGELOG.md` — what has changed so far

## Tracking: three files, three jobs

| File | Answers | Update when |
|------|---------|-------------|
| `context/progress-tracker.md` | *Where are we?* — current phase, what is built, next steps | After each meaningful change. Describe what is built, not what is intended. |
| `context/issue-tracker.md` | *What is open?* — bugs, tasks, questions, tech debt, each with an `ISS-NNN` id | When you find a bug, a gap, or an unanswered question; when you start, block, or close one. |
| `CHANGELOG.md` | *What changed?* — a dated record of changes | Every commit that changes behaviour, config, schema, prompts, or docs that others rely on. |

Rules:

- Never drop a question or bug on the floor: if you can't resolve it now, open an issue before continuing.
- Reference issue ids in commits, specs, and changelog entries (`ISS-006`).
- Closing an issue moves it to **Closed** with a one-line resolution; never delete it.
- Changelog entries go under **Unreleased**. When a phase's "Done when" passes, move them to a release heading (see `CHANGELOG.md`).

## Keeping docs in sync

- If a change alters architecture, storage, guard behaviour, or an invariant, update `docs/architecture.md` first; if the decision is hard to reverse, add an ADR.
- Never break an invariant in `docs/architecture.md` §11 without an ADR that says why.
- New domain terms go in `GLOSSARY.md` before they appear in code.

## Git

- Branch `main`; remote `shashank934602/secure-rag`.
- Commit messages: imperative summary line, then a short body listing what changed and the issue ids.
- No AI or tool attribution in commits, PR descriptions, or repo files (no co-author trailers, no "generated with" lines).
- Never commit `.env` or any secret; `.env.example` lists the keys.

## Commands

- Run from this folder. Python 3.12 via `uv`; deps in `pyproject.toml`.
- Install / sync: `uv sync`. Add a dep: `uv add <pkg>` (dev: `uv add --dev <pkg>`).
- Tests: `uv run pytest`. Lint: `uv run ruff check .`
