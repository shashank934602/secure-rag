# Project Overview

## What it is

A question-answering assistant over a company's private documents. Users ask in plain English; the system answers only from documents they are allowed to read, cites every claim, refuses manipulation attempts, and records why each answer was given or refused. Full design: `docs/architecture.md`.

## Why it exists

Portfolio project to demonstrate production-grade LLM engineering: retrieval quality, data security, auditability, and measurable evaluation — the parts most RAG demos skip.

## Goals

1. Answer from permitted documents only, with valid citations, or return a No-Answer.
2. Make cross-tenant and cross-role leakage impossible by construction (RLS + query filter), and prove it with canary tests.
3. Resist direct and indirect prompt injection with structural controls, not only classifiers.
4. Mask PII for users without `pii:read`; never log raw PII.
5. Keep a tamper-evident audit trail of every guard verdict.
6. Gate every change on an evaluation suite (quality + security + latency).

## Core user flows

1. **Uploader** uploads a document with an ACL → it is chunked, scanned, embedded, and becomes searchable (or quarantined).
2. **Reader** asks a question → receives a grounded answer with citations, a No-Answer, or a Refusal.
3. **Auditor** looks up any request in their tenant and sees every guard verdict; verifies the hash chain.
4. **Developer** opens a PR → the eval gate runs and reports quality, security, and latency deltas.

## In scope

- Single-turn Q&A over PDF / DOCX / Markdown / HTML.
- Multi-tenant, role-based document access.
- Guards, audit trail, eval pipeline, Docker Compose deployment.

## Out of scope (for now)

- Chat history / multi-turn conversations.
- Agents with tools (the LLM deliberately has none).
- Fine-tuning; a UI beyond a minimal page or API docs.
- Kubernetes, SSO/SAML, WORM audit storage (listed as limitations).
