# ACL copied onto chunks, enforced by RLS and query filter

The document is the source of truth for its ACL, but `tenant_id` and `allowed_roles` are copied onto every chunk so the vector query can filter without a join. Any ACL change updates the document and all of its chunks in a single transaction (`PATCH /v1/documents/{id}/acl`). Tenant isolation is additionally enforced by Postgres Row-Level Security (`SET LOCAL app.tenant_id` per request), so a missing `WHERE` clause in application code still cannot return another tenant's rows.

## Considered Options

- **Join to `documents` at query time**: always consistent, but defeats filtered HNSW search performance.
- **Filter after retrieval in Python**: simplest, but one bug leaks data and top-k shrinks unpredictably. Rejected.
