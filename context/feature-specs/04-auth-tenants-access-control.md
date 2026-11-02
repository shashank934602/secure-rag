# 04 — Auth, tenants, and access control

## Goal

Make leaking another company's (or another role's) documents **impossible by construction**, not just unlikely: the
database enforces tenant isolation with **Row-Level Security**, every request is **authenticated** and runs as a real user
whose roles come from the database, and a document's audience can be changed safely. Proven by leakage tests, including
one where the application's tenant filter is deliberately removed and the database still refuses to leak.

## Decisions (2026-11-02 — recommended options taken, learner chose "build now, study later")

| # | Decision |
|---|----------|
| D1 | **RLS** on `documents`, `chunks`, `users` (migration `0003`): policy `tenant_id = current_setting('app.tenant_id')`. With no tenant set, the setting is empty → **no rows** (fail closed). `tenants` has no RLS (names only; the app needs it to resolve a tenant). `rag_app` is not a superuser and has no BYPASSRLS (Phase 2 D3), so the policy applies to it. |
| D2 | **Tenant scope**: every app query on those tables runs inside `tenant_scope(conn, tenant_id)` — a transaction that does `SET LOCAL app.tenant_id`. LOCAL means the setting dies with the transaction, so a pooled connection can't carry one tenant's scope into the next request. |
| D3 | **Second tenant** "Northgate Haulage" (fake) seeded by `0003`, with its own small corpus in `data/tenants/northgate/` containing **canary** strings (`CANARY-NG-…`). Aldermoor's roles become `{employee, hr}`; an **HR-only** document (`data/tenants/aldermoor-hr/`) tests role filtering. `python -m app.ingest --tenant NAME --folder PATH --roles r1,r2`. |
| D4 | **Users** seeded by `0003` (fake `example.com`): Aldermoor `alice` (employee), `harriet` (employee, hr; permission `uploader`), Northgate `ned` (employee). `users` gains `permissions text[]`. Roles = which documents you can read; permissions = what you can do (GLOSSARY). |
| D5 | **Auth**: JWT (HS256, `JWT_SECRET` in `.env`) with only `sub` (user id), `tenant` (tenant id), and `exp`. **Roles and permissions are loaded from the database on every request**, so removing a role takes effect immediately. Missing, invalid, or expired token, or unknown user → **401**. Dev tokens: `python -m app.auth token --tenant NAME --email EMAIL`. |
| D6 | `POST /v1/ask` requires a bearer token and answers **as that user** (tenant + roles). `GET /healthz` stays open. |
| D7 | `PATCH /v1/documents/{doc_id}/acl` `{allowed_roles}`: needs the `uploader` permission (else 403); roles must be a non-empty subset of the tenant's roles (else 422); a document of another tenant is invisible under RLS, so it's a **404**, which reveals nothing. The document and all its chunks change **in one transaction** (Invariant 2, ADR-0002). |
| D8 | Retrieval takes an **access scope** (tenant id + roles): `search(question, k, scope)`. The CLI and eval use the scope from settings (Aldermoor, employee); the API uses the authenticated user's. |
| D9 | **Deferred**: upload endpoint + ingestion jobs + worker (ISS-039) and Redis rate limiting (ISS-040). Not needed for this phase's "done when"; ingestion stays a command. Revisit before production. |
| D10 | Leakage tests (db): tenant A never retrieves tenant B in any search mode; a query **without** a tenant filter still returns only the scoped tenant (RLS); no scope → nothing; a removed role retrieves nothing; ACL change takes effect at once. API tests: 401s, 403, 404, answering as the right user. Real check: `python -m eval.leakage` asks Northgate-targeted questions as Aldermoor and fails on any canary in sources or answers. |

## Slices

| Slice | Issue | What |
|-------|-------|------|
| S1 | ISS-035 | RLS migration, tenant scope, Northgate + canaries, HR-only doc, ingest options, scoped search |
| S2 | ISS-036 | JWT auth, users from the DB, `/v1/ask` as the user |
| S3 | ISS-037 | `PATCH /v1/documents/{doc_id}/acl` |
| S4 | ISS-038 | Leakage check with real models, docs, release `v0.4.0` |

## Scope limits

- No upload endpoint, jobs, worker, or rate limiting (D9). No login UI: tokens are issued by a dev command.
- No guards or PII masking (Phase 5); no audit tables (Phase 6). The CLI stays a local, trusted tool.

## Check when done

- With `app.tenant_id` unset, `rag_app` sees no documents or chunks; with it set, only that tenant's rows, **even with no `WHERE tenant_id`** in the query.
- Searching as Aldermoor never returns a Northgate chunk; searching as `employee` never returns an `hr` chunk.
- `/v1/ask`: 401 without or with a bad token; answers as the token's user. `PATCH …/acl`: 403 without `uploader`, 404 for another tenant's document, 422 for an unknown role; document and chunks change together.
- `python -m eval.leakage`: 0 canaries leaked.
- The Phase 3 eval still passes unchanged (quality didn't drop).
