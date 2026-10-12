# Postgres + pgvector as the single store

Chunks, embeddings, ACLs, ingestion jobs, requests, and audit events all live in one Postgres 16 database with pgvector, instead of a dedicated vector DB (Qdrant, Pinecone) plus a separate relational DB and job queue. One store lets tenant isolation (RLS), ACL filtering, keyword search (`tsvector`), and audit writes share transactions and one security model; at portfolio and small-company scale pgvector's HNSW is fast enough.

## Consequences

- Filtered ANN search can return fewer than k rows when the role filter is selective; requires pgvector ≥ 0.8 iterative scan.
- Moving to a dedicated vector DB later means re-implementing ACL filtering and losing transactional ACL updates (see ADR-0002).
