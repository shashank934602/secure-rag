# Store raw text; mask PII at query time by permission

Chunks keep their raw text and are embedded from it; PII is only *detected* at ingest (stored as `pii_types`) and *masked* at query time, before the LLM sees the chunk, for users without `pii:read`. Masking at ingest would permanently remove information that authorized users legitimately need and would hurt retrieval for questions about people and contacts. Only an allow-list of sensitive entity types is masked (EMAIL, PHONE, SSN, IBAN, CREDIT_CARD, …), not every PERSON/ORG/LOCATION.

## Consequences

- The database holds raw PII, so encryption at rest, RLS, and restricted DB credentials are required.
- Logs, traces, and audit tables must only ever receive redacted text (Invariant 5).
