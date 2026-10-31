# Secure RAG Assistant

Answers questions from a tenant's private documents, only from what the asking user is allowed to see, and records why every answer was given or refused.

## Access

**Tenant**:
An organization whose documents, users, and audit trail are fully isolated from every other tenant.
_Avoid_: org, account, customer

**Role**:
A named group of users inside a tenant (e.g. `finance`, `hr`) that a document can be shared with.
_Avoid_: group, team

**Permission**:
A capability granted to a user independent of document access, such as `pii:read`, `uploader`, or `auditor`.
_Avoid_: scope, right

**ACL**:
The tenant plus the set of roles allowed to read a document.
_Avoid_: sharing settings, visibility

## Knowledge base

**Document**:
One uploaded file at one version, with an ACL.
_Avoid_: file, source

**Doc id**:
A document's short, human-readable identifier, the slug of its filename (e.g. `leave-policy`), unique within a tenant; the `doc_id` in citations.
_Avoid_: document name, file id

**Chunk**:
A contiguous slice of a document's text that is embedded and retrieved as a unit; inherits the document's ACL.
_Avoid_: passage, segment, split

**Content hash**:
A SHA-256 fingerprint of a document's bytes; if it hasn't changed, re-ingesting the document is skipped.
_Avoid_: checksum, etag

**Ingest**:
Load, chunk, embed, and store a document's chunks so they can be retrieved; re-running it on unchanged documents changes nothing.
_Avoid_: index (as a verb), import, sync

**Retriever**:
Anything with `search(question, k)` that returns the k most similar chunks with scores; in-memory for unit tests, Postgres in the app.
_Avoid_: search engine, vector store (that is one implementation detail)

**Corpus version**:
A counter that increases whenever any document in a tenant is added, changed, or removed.
_Avoid_: index version

**Quarantined document**:
A document held back from retrieval because a chunk was flagged for embedded instructions.
_Avoid_: blocked doc, rejected doc

**Canary**:
A unique string planted in one tenant's test documents that must never appear in another tenant's answers.

## Answering

**Keyword search**:
Finding chunks that contain the question's words (Postgres full text, `content_tsv`); good at exact names and rare terms.
_Avoid_: text search, grep

**Hybrid search**:
Dense (meaning) search and keyword search run together, their ranked lists combined with Reciprocal Rank Fusion.
_Avoid_: combined search

**RRF (Reciprocal Rank Fusion)**:
Combines ranked lists by summing 1 / (60 + rank) per chunk, so a chunk ranked well by either search rises; scores aren't compared directly.
_Avoid_: score averaging

**Candidate**:
A chunk returned by hybrid search, before reranking.

**Reranker**:
A cross-encoder model that reads the question and a candidate together and scores relevance 0–1; more precise than embeddings, too slow for the whole corpus.
_Avoid_: re-scorer, ranker

**Relevance threshold**:
The minimum best reranker score for the system to try answering; below it, the answer is a No-Answer without calling the LLM.
_Avoid_: cutoff, confidence

**Citation**:
A reference `[doc_id:page]` in an answer that must point to a chunk retrieved for that request.
_Avoid_: source link, reference

**Grounded answer**:
An answer in which every claim is supported by a cited chunk.
_Avoid_: correct answer (correctness is measured separately against the golden set)

**No-Answer**:
The outcome when the permitted documents don't contain the answer; a success, not an error.
_Avoid_: fallback, empty answer

**Refusal**:
The outcome when a guard blocks the request.
_Avoid_: rejection, block

## Guards and audit

**Guard**:
A check that runs at a fixed point in the request flow and returns a guard verdict.
_Avoid_: filter, validator, guardrail (use "guardrails" only for the whole set)

**Guard verdict**:
A guard's decision (`ALLOW`, `DROP`, `MASK`, `PASS`, `FAIL`, `BLOCK`) with a score and reason.

**Fail closed**:
Treat an unavailable or timed-out guard as a refusal rather than skipping it.

**Audit event**:
One append-only, hash-chained record of a guard verdict or stage outcome for a request.
_Avoid_: log line, trace

**Audit trail**:
All audit events for a tenant, in hash-chain order.

## Evaluation

**Golden set**:
Questions with expected answers and expected source documents.

**Adversarial set**:
Requests designed to make the system leak, obey injected instructions, or exfiltrate data.

**Benign set**:
Ordinary questions used to measure false refusals.

**Eval gate**:
The thresholds a change must meet in CI before it can merge.

**Baseline**:
The eval scores of a fixed, committed version (`eval/baselines/phase2.json`); later changes are compared against it.
_Avoid_: benchmark, reference run

**Key fact**:
A short phrase an answer must contain to count as correct (e.g. `25 days`); answer correctness is the share of key facts found.
_Avoid_: keyword, expected token

**Recall@5**:
For an answerable question, the share of its expected sources (`doc_id:page`) that appear in the top 5 retrieved chunks.
_Avoid_: hit rate, accuracy

**MRR (mean reciprocal rank)**:
The average of 1 / (rank of the first expected source in the results), or 0 when none is found; rewards putting the right chunk first.
_Avoid_: average rank

## Operations

**Migration**:
A versioned, ordered SQL change to the database schema (`db/migrations/`), applied by Alembic; never edited after it has been applied.
_Avoid_: schema update, DDL script

**App role**:
The non-superuser database role `rag_app` the application connects as; it can read and write rows but cannot bypass row-level security or change the schema.
_Avoid_: db user, service account
