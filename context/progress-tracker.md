# Progress Tracker

Update after every meaningful change. Describe what is actually built, not what is intended.

## Current phase

**Phase 1 — basic RAG pipeline** (`context/feature-specs/01-basic-rag-pipeline.md`). Spec grilled and decided (D1–D16).
Slices 1–2 done (ISS-009, ISS-010). Working on slice 3 (ISS-011): embeddings + search. Phase 0 leftover: ISS-005 (workflow skills).

## Completed

- **Phase 1 slice 2 — loading + chunking** (2026-10-12, ISS-010)
  - `app/ingestion/loaders.py`: `load_pages(folder)`; MD = page 1, PDF = one page per PDF page (1-based, empty pages skipped); hidden files ignored; other types and duplicate doc ids raise.
  - `app/ingestion/chunking.py`: `chunk_pages(...)`; per-page token chunks via `tiktoken` `cl100k_base`.
  - `app/config.py` (`Settings`, `get_settings()`), `app/domain.py` (`Page`, `Chunk`).
  - Tests: 10 passing (`uv run pytest`), ruff clean. Real corpus: 11 documents, 13 pages, 23 chunks.
- **Phase 1 slice 1 — sample corpus + golden set** (2026-10-12, ISS-009)
  - `data/sample/`: employee handbook; annual leave, sickness absence, expense, IT security, health and safety, remote work policies; CleanFleet and TrackLine contracts; org chart (Markdown); SwiftParts contract (3-page PDF). ~5,900 tokens, 23 chunks at 400/50.
  - Fake data only: `aldermoor.example.com` / `*.example.com` emails, `555-01xx` phones, `AF-` employee ids.
  - `eval/datasets/golden.jsonl`: 10 entries; every expected fact checked against its cited page; near-miss topics confirmed absent.
- **Phase 0 — Setup** (2026-10-12)
  - Own Git repo (`main` branch) in this folder, pushed to `https://github.com/shashank934602/secure-rag`.
  - `uv` project, Python pinned to 3.12 (`.python-version`, `requires-python = ">=3.12,<3.13"`).
  - Phase 1 deps: `langchain`, `langchain-core`, `langchain-openai`, `langchain-groq`, `langchain-text-splitters`, `pypdf`, `pydantic`, `pydantic-settings`, `python-dotenv`. Dev: `pytest`, `ruff`.
  - `.env` (gitignored) with Groq, OpenAI, Hugging Face, Google, Mistral keys; `.env.example` committed.
  - Check passes: `uv run python -c "import langchain"` (langchain 1.4.4 on Python 3.12.14).
  - Tracking: `AGENTS.md` (agent entry point, Arch-AI pattern), `context/issue-tracker.md`, `CHANGELOG.md`.
- **Design** (2026-10-10)
  - `docs/architecture.md`: HLD, ingestion, LangGraph flow, sequence, latency budget, guardrails, data model, API, eval pipeline, deployment, invariants, limitations.
  - Independent design review applied: latency/streaming contradiction, ACL staleness + RLS, PII masking moved to query time, audit hash chain + start row, tenant-scoped audit/upload authorization, cache rules, structural injection controls, hybrid search, early eval harness.
  - ADRs 0001–0004, `GLOSSARY.md`, context files.

## Decisions (Phase 0, from `plan.md` §9)

- Embedding model: OpenAI `text-embedding-3-small`, 1536-d → `vector(1536)`. `bge-small-en-v1.5` (384-d) is the offline fallback.
- Reranker hardware: CPU / Apple MPS on the M4; no GPU.
- Sample corpus: synthetic, LLM-generated, hand-edited; two tenants; fake PII; canary strings in tenant B.
- Separate repo: yes — `shashank934602/secure-rag` (public).
- Main chat model: Groq `openai/gpt-oss-120b`.
- Grounding judge: small model from a different family (Llama or Gemini Flash).

## Open questions

Tracked in `context/issue-tracker.md`.

## Next steps

1. ISS-009 → ISS-013: build Phase 1 in five slices, pushing after each.
2. ISS-005: resolve the workflow-skills question (Phase 1 uses the available `grilling` / `tdd` / `code-review` skills meanwhile).
