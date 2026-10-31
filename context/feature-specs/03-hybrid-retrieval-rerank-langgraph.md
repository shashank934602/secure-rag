# 03 — Hybrid retrieval, reranking, and a LangGraph flow

## Goal

Fix the retrieval misses the Phase 2 baseline found (g06, g17: the needed page ranks 6th and 7th, just below the top 5) by
widening the net and ordering it better: keyword search fused with vector search (**hybrid**), then a **cross-encoder
reranker** that picks the top 5 and decides relevance. Move the answering flow into a **LangGraph** state machine so later
phases can add guards as nodes. Prove it with the eval: **hybrid + rerank must beat dense-only**.

## Decisions (2026-10-31 — recommended options taken, learner chose "build now, study later")

| # | Decision |
|---|----------|
| D1 | Keyword search: Postgres full text. Migration `0002` adds `content_tsv` (generated `to_tsvector('english', content)`) with a GIN index. The question becomes an **OR** query of its words (`websearch_to_tsquery` with `or`), so a long question still matches; ranked by `ts_rank_cd`. (Postgres ranking is BM25-like, not BM25.) |
| D2 | Fusion: **Reciprocal Rank Fusion**, `score = Σ 1 / (60 + rank)` over the dense and keyword lists, 20 candidates each → top 20 fused. Pure function, unit-tested. |
| D3 | Same security filters on both searches: tenant, `is_active`, role overlap (Invariant 1 query filter). |
| D4 | Reranker: `BAAI/bge-reranker-base` cross-encoder via `sentence-transformers`, on CPU/MPS, scores in 0–1 (sigmoid). Reranks the 20 candidates → top 5. Behind a `Reranker` protocol with a keyword fake for tests. |
| D5 | Relevance threshold: if the best reranker score is below `rerank_threshold`, return No-Answer **without calling the LLM**. The value is calibrated on the golden set and recorded with its numbers; with only 20 questions it is a starting point, not a tuned constant. |
| D6 | LangGraph graph: `retrieve → rerank → (no_answer \| generate) → check_citations → (respond \| generate again, once) `. Invalid citations get one retry, then No-Answer. `Answerer.answer(question)` keeps its signature, so the CLI, API, and eval don't change. |
| D7 | Config switches for the comparison: `retrieval_mode = dense \| hybrid` and `rerank = true \| false`. Defaults after this phase: whatever the eval shows is best. |
| D8 | `ScoredChunk.score` means the last stage's score: similarity (dense), RRF (hybrid), or reranker relevance (reranked). The CLI `--debug` shows it. |
| D9 | Eval: run the golden set three times (dense; hybrid; hybrid + rerank), record all three in the changelog and tracker, save the best as `eval/baselines/phase3.json`. The report records the mode. |
| D10 | Tests: RRF and graph routing offline with fakes; keyword and hybrid search as `db` tests; the real reranker as a `live` test (it downloads a ~1 GB model). |

## Implementation

1. **Keyword + hybrid search** — migration `0002_content_tsv`; `PgRetriever(mode="dense" | "keyword" | "hybrid", candidates=20)`; `rrf_fuse()` in `app/retrieval/fusion.py`.
2. **Reranker** — `app/retrieval/rerank.py`: `Reranker` protocol, `CrossEncoderReranker` (loaded once), threshold in settings.
3. **LangGraph** — `app/answering/graph.py`: state, nodes, edges; `Answerer` runs the compiled graph.
4. **Eval comparison** — `python -m eval.run --mode …`; three runs; baseline `phase3.json`; release `v0.3.0`.

## Slices

| Slice | Issue | What |
|-------|-------|------|
| S1 | ISS-030 | `content_tsv` migration, keyword search, RRF fusion, hybrid mode |
| S2 | ISS-031 | Cross-encoder reranker + relevance threshold |
| S3 | ISS-032 | LangGraph answering flow with one citation retry |
| S4 | ISS-033 | Three-way eval, Phase 3 baseline, release `v0.3.0` |

## Scope limits

- No guards, no PII masking, no grounding judge (Phase 5); no query rewriting (single-turn API).
- No auth or RLS (Phase 4); filters stay in the query.
- No prompt change (`answer_v1`), so differences come from retrieval only.

## Check when done

- `alembic upgrade head` adds `content_tsv` + GIN index; existing chunks get it without re-embedding.
- Keyword search finds an exact rare word (e.g. `SafeSite`) that it should; hybrid returns the union, ordered by RRF.
- The reranker puts the relevant chunk first in a live test; below-threshold questions return No-Answer without an LLM call.
- The graph routes: no candidates → No-Answer; low relevance → No-Answer; invalid citations → one retry → No-Answer.
- Eval table for dense / hybrid / hybrid+rerank is recorded; hybrid+rerank ≥ dense on recall@5 and answered, with No-Answer accuracy not worse.
