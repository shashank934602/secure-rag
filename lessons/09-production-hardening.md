# Lesson 9 — Hardening: secrets, abuse, and identity

> Production Stage B, the parts that need no server. Spec: `context/feature-specs/09-production-hardening.md`.
> Built at pace (build now, study later). Every result here is real, from 2026-11-05.

## Why

Phases 1–8 made the assistant correct and safe *in its answers*. Production adds attackers who never ask a question: one who
finds a key in the git history, one who floods the API to run up the bill, one who steals a token. Stage B closes those
doors on one machine, before there is a server to attack.

## 1. Secrets: scan the history, not just today's files

A secret committed once lives in the git history **forever**, even after the file is deleted. We scanned all 111 commits
with **gitleaks**: 6 findings, all deliberate test fakes (now ignored by fingerprint, so a *new* secret in the same files is
still caught). Then we tested the scanner the way an attacker's mistake would happen, and it **missed a committed Groq key**:
its built-in rules have no Groq pattern. We added rules for Groq keys, Mistral keys, and committed `.env` files, and proved
each one fires. Lesson: **a security tool you haven't tested against your own failure is a guess.**

## 2. Dependencies and images: known holes

**pip-audit** compares every locked package with public advisories: 34 known issues in 3 packages, the worst in `pypdf`
(16), which parses uploaded PDFs, i.e. *untrusted input*. Upgraded; now 0. **trivy** scans the built image, including the
operating system underneath Python: 2 high issues in Debian's `apt`; the image now installs security updates at build time;
now 0 high, 0 critical. Both run in CI on every push (job "Supply chain").

## 3. Rate limits and a token budget

| Limit | Default | Over it |
|---|---|---|
| Per user | 20 requests a minute | 429 + `Retry-After` |
| Per tenant | 120 a minute | 429 |
| Tokens per tenant per UTC day | 200,000 (the Groq free tier) | 429 until midnight, **no model call** |

Counters live in **Redis**, a fast in-memory store, so several API processes share one count. Each counter has a lifetime,
so old windows clean themselves up. Live: requests 1–20 of a minute → 403 (alice isn't an auditor), request 21 → **429,
Retry-After 7**.

**Fail closed again:** with Redis stopped, requests got **503**, not unlimited access. A limiter that silently stops limiting
is worse than none, because nobody notices.

## 4. Tokens: RS256 and 15 minutes

Before: one shared secret both made and checked tokens (HS256), valid an hour. Now:

- **RS256**: a *private* key signs, a *public* key checks. Anything that only checks tokens can't make them.
- **The algorithm is pinned.** Three classic forgeries are refused: a token claiming `alg: none` (unsigned); an HS256
  token; and **algorithm confusion**: an attacker takes our *public* key (it's public!) and uses it as an HS256 secret.
  A library that trusts the token's own `alg` header would accept that.
- **`kid`** (key id) in each token's header: during a key rotation, the old public key stays accepted for 15 minutes
  while new tokens use the new key.
- **15 minutes**: a stolen token is useful briefly. Roles still come from the database on every request.

Live: a new token → 200; an old HS256 token signed with the real old secret → **401**.

## 5. Fingerprints per tenant

Questions are stored as an HMAC (a keyed fingerprint), never as text. With one key, the same question had the same
fingerprint in every company, so someone with the database could link them. Now each tenant's key is derived from the main
key and the tenant id: same question, unrelated fingerprints across tenants, still findable within one.

## Explain it back (later)

1. Deleting a file that held a key: why isn't that enough? What is?
2. Why did the scanner miss the Groq key, and how do you know your rules work now?
3. Why must the limiter refuse when Redis is down, instead of letting requests through?
4. Why check the token budget *before* the model call and count it *after*?
5. Explain "algorithm confusion" to a colleague in three sentences.
6. What does `kid` make possible that a single key can't?
