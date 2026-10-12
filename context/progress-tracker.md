# Progress Tracker

Update after every meaningful change. Describe what is actually built, not what is intended.

## Current phase

**Phase 0 — Setup**, nearly done. Remaining: ISS-007 (push to GitHub), ISS-005 (workflow skills), ISS-008 (doc cleanup).
Next: **Phase 1 — basic RAG pipeline** (`context/feature-specs/01-basic-rag-pipeline.md`).

## Completed

- **Phase 0 — Setup** (2026-10-12)
  - Own Git repo (`main` branch) in this folder; remote `https://github.com/shashank934602/secure-rag` (not yet pushed).
  - `uv` project, Python pinned to 3.12 (`.python-version`, `requires-python = ">=3.12,<3.13"`).
  - Phase 1 deps: `langchain`, `langchain-core`, `langchain-openai`, `langchain-groq`, `langchain-text-splitters`, `pypdf`, `pydantic`, `pydantic-settings`, `python-dotenv`. Dev: `pytest`, `ruff`.
  - `.env` (gitignored) with Groq, OpenAI, Hugging Face, Google, Mistral keys; `.env.example` committed.
  - Check passes: `uv run python -c "import langchain"` (langchain 1.4.4 on Python 3.12.14).
  - Tracking: `AGENTS.md` (agent entry point, Arch-AI pattern), `context/issue-tracker.md`, `CHANGELOG.md`.
- **Design** (2026-10-10)
  - `docs/architecture.md`: HLD, ingestion, LangGraph flow, sequence, latency budget, guardrails, data model, API, eval pipeline, deployment, invariants, limitations.
  - Independent review (Sonnet) applied: latency/streaming contradiction, ACL staleness + RLS, PII masking moved to query time, audit hash chain + start row, tenant-scoped audit/upload authorization, cache rules, structural injection controls, hybrid search, early eval harness.
  - ADRs 0001–0004, `GLOSSARY.md`, context files.

## Decisions (Phase 0, from `plan.md` §9)

- Embedding model: OpenAI `text-embedding-3-small`, 1536-d → `vector(1536)`. `bge-small-en-v1.5` (384-d) is the offline fallback.
- Reranker hardware: CPU / Apple MPS on the M4; no GPU.
- Sample corpus: synthetic, LLM-generated, hand-edited; two tenants; fake PII; canary strings in tenant B.
- Separate repo: yes — `shashank934602/secure-rag` (public).
- Main chat model: Groq `openai/gpt-oss-120b`.
- Grounding judge: small model from a different family (Llama or Gemini Flash).

## Open questions

Tracked in `context/issue-tracker.md` (open: ISS-005 … ISS-008).

## Next steps

1. ISS-008: decide on remaining AI-tool mentions, then ISS-007: push to GitHub.
2. ISS-005: resolve the workflow-skills question.
3. Grill Phase 1 (includes ISS-006), then implement `01-basic-rag-pipeline.md`.
