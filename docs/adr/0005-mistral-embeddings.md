# Mistral `mistral-embed` as the embedding model (1024-d)

Embeddings come from Mistral's `mistral-embed` (1,024 numbers per text) instead of OpenAI's `text-embedding-3-small` (1,536), which was chosen in Phase 0 (ISS-001). The OpenAI account had no credits (ISS-014) while the existing Mistral key worked on the free tier, and the project budget is under $20. Because every embedding client is created through one factory from a `provider:model` string, the switch was a one-line config change. It is recorded as an ADR because the vector dimension is fixed in the database schema from Phase 2 (`vector(1024)`): changing the model later means re-embedding every chunk.

## Considered Options

- **Keep OpenAI, add credits**: strong quality, small cost; rejected for now only because it blocked progress and costs money.
- **Local `BAAI/bge-small-en-v1.5` (384-d)**: free and offline, but needs PyTorch now and gives smaller vectors; kept as the offline fallback.

## Consequences

- Phase 2 schema uses `vector(1024)`; `embedding_model` is stored per chunk so a future switch is detectable.
- Chunk sizes are still measured with `tiktoken` `cl100k_base`; Mistral counts tokens slightly differently, which is safe because 400 tokens is far below `mistral-embed`'s 8,192-token input limit.
- The free tier is rate-limited (seen on 2026-10-15); evaluation runs must pace their requests.
- Before real personal data is used, Mistral's data-use terms must be checked (production plan D-P6).
- Retrieval quality is measured, not assumed: recall@5 on the golden set is the deciding number.
