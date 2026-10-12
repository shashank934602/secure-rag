# 01 — Basic RAG pipeline

## Goal

Answer a question from a small folder of local documents, with citations, in a single Python script. No database, no API, no guards yet. This is the skeleton every later phase hardens.

## Implementation

1. **Sample corpus** — add 5–10 synthetic documents under `data/sample/` (Markdown and one PDF): a company handbook, a leave policy, an expense policy, a vendor contract. Include a few fake emails and phone numbers for later PII work.
2. **Load** — load every file in `data/sample/` with the matching LangChain loader; keep `source` and `page` metadata.
3. **Chunk** — `RecursiveCharacterTextSplitter`, ~800 tokens, 100 overlap. Give each chunk an id `doc_id:page:index`.
4. **Embed + store** — embed chunks with the embeddings factory (full model dimension, not 64) into an in-memory vector store.
5. **Retrieve** — top-5 by similarity for the question.
6. **Generate** — prompt from `app/prompts/answer_v1.md`: answer only from the provided documents, cite `[doc_id:page]` after each claim, otherwise reply with the No-Answer sentence. Chunks wrapped in `<document id="…">` tags.
7. **Validate citations** — every cited id must be among the retrieved chunks; otherwise return No-Answer.
8. **CLI** — `python -m app.cli "question"` prints the answer and the cited sources.

## Scope limits

- No Postgres, no FastAPI, no LangGraph, no auth, no guards, no audit.
- No reranker, no hybrid search.
- Don't build an eval harness yet (Phase 2), but write down 10 questions with expected answers and sources in `eval/datasets/golden.jsonl` while creating the corpus.

## Check when done

- A question answered in the corpus returns an answer with at least one valid citation.
- A question not answered in the corpus returns the No-Answer sentence.
- An answer citing an id that wasn't retrieved is converted to No-Answer (test with a fake LLM).
- Changing the chat model in config to another provider works without code changes.
- `eval/datasets/golden.jsonl` has 10 entries.
