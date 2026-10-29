# System map — what happens, and where it happens

> A concept map of the whole system as it is built today (Phase 2, S1–S2 done; S3 in progress).
> For each step: the **idea**, the **file** that does it, the **place** it runs, and a **real example** from our data.

---

## The four places things happen

```
┌──────────────────────────── YOUR MAC ─────────────────────────────┐        ┌──── INTERNET ────┐
│                                                                    │        │                  │
│  ① Python program (app/)          ② Docker container "db"         │  ───▶  │ ③ Mistral        │
│     your terminal runs it            Postgres + pgvector, :5433    │        │   text → 1,024   │
│     reads data/sample/               tables: documents, chunks     │        │   numbers        │
│                                                                    │  ───▶  │ ④ Groq           │
│                                                                    │        │   the LLM writes │
│                                                                    │        │   the answer     │
└────────────────────────────────────────────────────────────────────┘        └──────────────────┘
```

| Place | What lives or happens there |
|-------|-----------------------------|
| ① Python on your Mac (`app/`) | all our logic: loading, chunking, the prompt, citation checks |
| ② Docker database on your Mac | the stored chunks and their vectors (11 documents, 23 chunks) |
| ③ Mistral's servers | turns text into 1,024 numbers (embeddings). Stores nothing for us |
| ④ Groq's servers | the LLM (`gpt-oss-120b`) that reads the prompt and writes the answer |

**Concept: what leaves your machine.** Document text goes to **Mistral** (to be embedded), and the question plus 5 chunks
go to **Groq** (to be answered). With fake documents, that's fine. With a real company's documents, it's a privacy decision:
providers must not keep or train on the data (production decision D-P6). The database never leaves your Mac.

---

## Journey A — putting documents in (ingest)

Runs **once**, and again only when documents change. Command: `uv run python -m app.ingest`

| # | What happens | Concept | Where (file → function) | Place | Real example |
|---|--------------|---------|-------------------------|-------|--------------|
| A1 | read every file into pages | loading | `app/ingestion/loaders.py` → `load_pages` | ① | 11 files → 13 pages (the PDF has 3) |
| A2 | fingerprint each file | hashing | `app/ingest.py` → `_fingerprint` | ① | leave policy = `c199c3e2617b…`; same as stored → **skip** |
| A3 | cut pages into pieces | tokens, chunking | `app/ingestion/chunking.py` → `chunk_pages` | ① | 13 pages → 23 chunks of ≤ 400 tokens |
| A4 | turn each chunk into numbers | embeddings | `app/retrieval/embeddings.py` → `make_embeddings` | ③ | each chunk → 1,024 numbers |
| A5 | save document + chunks | transactions | `app/ingest.py` → `_replace_document` | ② | all-or-nothing per document |

Result in the database: `documents` = 11 rows, `chunks` = 23 rows. 1st run 9.6 s; 2nd run 0.7 s (nothing changed, nothing re-sent).

---

## Journey B — asking a question

Runs **every time**. Command: `uv run python -m app.cli "How many days of annual leave do I get?"`

| # | What happens | Concept | Where (file → function) | Place | Real example |
|---|--------------|---------|-------------------------|-------|--------------|
| B1 | read the question | — | `app/cli.py` → `main` | ① | 10 tokens |
| B2 | turn the question into numbers | embeddings | the retriever calls Mistral | ③ | → 1,024 numbers |
| B3 | find the 5 closest chunks | retrieval, similarity | **today:** `app/retrieval/search.py` → `ChunkIndex.search` (in memory). **After S3:** `app/retrieval/pg_search.py` → `PgRetriever.search` (SQL) | today ①, after S3 ② | best score 0.850 (leave policy) |
| B4 | build the prompt: rules + chunks + question | prompt | `app/answering/answer.py` → `_user_message`, rules in `app/prompts/answer_v1.md` | ① | 134 + 1,394 tokens |
| B5 | the LLM writes an answer | generation | `chat_model.invoke` in `app/answering/answer.py` | ④ | "25 days … [annual-leave-policy:1]" |
| B6 | check the citations | distrust the output | `app/answering/citations.py` → `parse_citations`, `all_citations_retrieved` | ① | made-up source → "I don't know" |
| B7 | print answer + sources | — | `app/cli.py` → `_format` | ① | `Sources: annual-leave-policy:1` |

---

## The gap S3 closes

```
Journey A ──▶ [ database: 23 chunks + vectors ]        ← filled ✅
Journey B ──▶ [ in-memory copy, rebuilt every run ]     ← still used today
                    ▲
                    └── S3's SQL query is the bridge: B3 reads from the database instead
```

Today, every question **re-embeds all 23 chunks** (23 texts sent to Mistral) just to search them. After S3, a question
sends **1** text (the question itself), because the chunks' numbers are already stored. That's the whole point of the database.

What the S3 query does, inside Postgres (place ②), in the order the database runs it:

1. **JOIN** each chunk to its document, to get its name (`slug`) and file (`source`).
2. **WHERE** keep only this company's, active, role-allowed chunks: *security*.
3. **ORDER BY** distance `<=>`, closest first: *search*, using the HNSW index.
4. **LIMIT** k: the top 5.
5. **SELECT** with `score = 1 − distance`: *similarity*, where 1 means same meaning.

---

## Where to look yourself

| Folder | Holds |
|--------|-------|
| `data/sample/` | the 11 fake company documents |
| `app/ingestion/` | loading and chunking (A1, A3) |
| `app/ingest.py` | the ingest command (Journey A) |
| `app/retrieval/` | embeddings and the two searches (A4, B2, B3) |
| `app/answering/` | prompt, LLM call, citation checks (B4–B6) |
| `app/prompts/` | the rules given to the LLM |
| `db/migrations/` | the database's tables (S1) |
| `tests/` | proof that each step does what it should |
| `lessons/` | these notes |

## Check questions

1. Which two outside companies see your document text, and at which steps?
2. After S3, how many texts are sent to Mistral for one question: 23 or 1? Why?

<details><summary>Answers</summary>

1. Mistral at A4 (every chunk, during ingest) and B2 (the question); Groq at B5 (the question plus the 5 retrieved chunks).
2. One: the question. The chunks were embedded once during ingest and their numbers are stored in the database, so
   search only needs the question's numbers.
</details>
