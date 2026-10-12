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
| ISS-006 | Spec 01 chunk size: "~800 tokens" vs `RecursiveCharacterTextSplitter` (counts characters) | question | 1 | P2 | open | 2026-10-12 | Use a token length function, or restate the size in characters. Decide when grilling Phase 1. |

## Closed

| Id | Title | Type | Phase | Opened | Closed | Resolution |
|----|-------|------|-------|--------|--------|------------|
| ISS-001 | Embedding model: OpenAI `text-embedding-3-small` or local `bge-small-en-v1.5`? | question | 0 | 2026-10-10 | 2026-10-12 | `text-embedding-3-small`, 1536-d → `vector(1536)`. `bge-small` is the offline fallback. |
| ISS-002 | Reranker hardware: CPU only, or GPU? | question | 0 | 2026-10-10 | 2026-10-12 | CPU / Apple MPS on the M4; no GPU. |
| ISS-003 | Sample corpus: which documents? | question | 0 | 2026-10-10 | 2026-10-12 | Synthetic, LLM-generated, hand-edited; two tenants; fake PII; canary strings in tenant B. |
| ISS-004 | Should this folder be its own Git repo? | question | 0 | 2026-10-10 | 2026-10-12 | Yes — `shashank934602/secure-rag` (public), branch `main`. |
| ISS-008 | Remove remaining AI-tool mentions from tracked docs | task | 0 | 2026-10-12 | 2026-10-12 | Rewrote `plan.md` §4.6 install line and the design-review line neutrally. |
| ISS-007 | Push initial repo to GitHub | task | 0 | 2026-10-12 | 2026-10-12 | Pushed `main` to `shashank934602/secure-rag`. |
