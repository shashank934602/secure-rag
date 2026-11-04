# 08 — Ship it

## Goal

Make the project something a stranger can clone, run, and understand in ten minutes. One command starts the database,
applies the migrations, loads both companies' demo documents, and serves the API and a small web page; a README explains
the problem, the architecture, the measured results, how to run it, and its limits. **Done when** a stranger, following
only the README on a fresh clone, has the stack running and an answered question with citations in ≤ 10 minutes (keys in
hand, model downloads excluded), and the tester confirms it.

## Decisions (2026-11-04 — recommended options taken, "build now, study later")

| # | Decision |
|---|----------|
| D1 | **`docker compose up` starts everything**: `db` (Postgres + pgvector, as today), `migrate` (one-shot: `alembic upgrade head`), `seed` (one-shot: ingest every demo folder for both tenants, safe to re-run, then print demo tokens), `api` (uvicorn). Order is enforced with `depends_on` conditions (healthy / completed successfully). Development keeps `docker compose up -d db` for the database alone. |
| D2 | **One image** (`Dockerfile`) for `migrate`, `seed`, and `api`: Python 3.12 slim, dependencies from `uv.lock` (`uv sync --locked --no-dev`, CPU PyTorch on Linux), non-root user, no secrets baked in. The local models download on first use into a named volume (`hf-cache`), so rebuilding the image doesn't re-download them. |
| D3 | **Ports stay on 127.0.0.1** (no rate limiting yet, ISS-040): API `127.0.0.1:${API_PORT:-8000}`, database `127.0.0.1:${DB_PORT:-5433}`. Inside the compose network the services use `db:5432`. |
| D4 | **Setup without secrets in the repo**: `python3 scripts/make_env.py` creates `.env` from `.env.example`, generating every local secret (database passwords, `JWT_SECRET`, `AUDIT_HMAC_KEY`) and never printing one; the person only pastes `GROQ_API_KEY` and `MISTRAL_API_KEY` (both free tiers). Existing values are never overwritten. A new `RAG_APP_PASSWORD` lets compose build the in-network `DATABASE_URL`. |
| D5 | **A minimal web page at `/`** (ISS-056, partly): paste a token, ask a question, see the answer, its status (answered / No-Answer / refused), its citations with sources, and the request id. Plain HTML + one script file served by the API; answers are inserted as text, never HTML; a strict Content-Security-Policy (`default-src 'self'`). The token is kept in `sessionStorage` (gone when the tab closes). No login form: tokens come from the `seed` output or the CLI, so no new way to obtain one is added. |
| D6 | **README** (root): the problem in three sentences, an architecture diagram (Mermaid, renders on GitHub), the **results table** from the committed baselines (security and quality, with intervals and honest misses), quick start, development commands, limitations, and a map of the docs and lessons. A CI badge. |
| D7 | **Demo video**: `docs/demo-script.md`, a timed 2–3 minute script with every command and click (the owner records it; ISS-069). The blog post stays optional. |
| D8 | **Release** `v0.8.0`, not `v1.0.0`: the plan's phases end here, but production (rate limiting, key management, RS256, monitoring) is the next stage (`docs/production-plan.md`). |

## Slices

| Slice | Issue | What |
|-------|-------|------|
| S1 | ISS-065 | `Dockerfile`, compose stack (`migrate`, `seed`, `api`), `scripts/make_env.py`, `RAG_APP_PASSWORD`; works from a fresh clone |
| S2 | ISS-066 | Web page at `/` with CSP; tests |
| S3 | ISS-067 | README, demo script, AGENTS.md commands |
| S4 | ISS-068 | Lesson 8, tester (fresh-clone, 10-minute test), release `v0.8.0` |

## Scope limits

- No hosting, TLS, or public deployment (production plan); everything binds to 127.0.0.1.
- No user accounts or login UI; tokens as today. No streaming answers (ADR-0003).
- The seeded data is the fake demo corpus only.

## Check when done

- From a fresh clone: `python3 scripts/make_env.py`, paste two keys, `docker compose up` → healthy API, seeded data, tokens printed; the web page answers a question with citations.
- Re-running `docker compose up` (or `seed`) changes nothing (idempotent ingest).
- The README's numbers match `eval/baselines/`; every command in it was run.
- All suites green; CI green; the tester's report is in `docs/test-reports/`.
