# Code Standards

## General

- Keep modules small in interface and deep in behaviour: callers should need to know very little (see the `codebase-design` skill).
- Fix root causes; don't layer workarounds.
- Name files after the responsibility they contain, not the technology (`hybrid_search.py`, not `pgvector_utils.py`).
- Use `GLOSSARY.md` terms in names: `Chunk`, `GuardVerdict`, `Citation`, `NoAnswer`, not synonyms.

## Python

- Type hints on every function; no `Any` at module interfaces.
- Pydantic models for all data crossing a boundary (HTTP, DB rows, LLM structured output, eval datasets).
- Validate external input before any logic runs.
- Configuration through `pydantic-settings`; model names, thresholds, and timeouts live in config, never inline.
- All LLM and embedding clients created through `init_chat_model` / one embeddings factory, so providers stay swappable and tests can inject fakes.

## API

- Handlers are thin: validate → check role and tenant → call one module → return a consistent response shape.
- Auth and tenant checks happen before any read or mutation.
- Long-running work (ingestion) goes to the worker, never inside a request handler.

## Data and security

- Set the tenant with one helper (`SET LOCAL app.tenant_id`) at the start of every DB transaction; no query on tenant data runs without it.
- SQL that touches `chunks` lives only in `app/retrieval/` and `app/ingestion/`; SQL that touches `audit_events` lives only in `app/audit/`.
- Never log, trace, or print raw questions, raw answers, or unmasked chunk text. Use the redaction helper.
- Migrations are append-only: never edit an applied migration; add a new one.
- Prompts live in `app/prompts/` as versioned files; the version is recorded on each request.

## Tests

- Test behaviour through module interfaces at agreed seams (see `context/ai-workflow-rules.md`), not internals.
- Unit and integration tests use a fake LLM and fake embeddings; real-model quality is measured by `eval/`, not by unit tests.
- Every security invariant in `docs/architecture.md` §11 has at least one test that would fail if it were broken.
