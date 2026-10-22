"""Ingest the corpus folder into Postgres (spec 02 step 3, ISS-021).

    uv run python -m app.ingest

For each document: same fingerprint as stored → skipped; new or changed → chunked, embedded, and
its chunks replaced in one transaction; a document whose file is gone → deleted with its chunks.
Running it twice changes nothing the second time.
"""

import argparse
import hashlib
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from langchain_core.embeddings import Embeddings

from app.config import Settings, get_settings
from app.db import connect
from app.domain import Page
from app.ingestion.chunking import chunk_pages
from app.ingestion.loaders import load_pages
from app.retrieval.embeddings import make_embeddings


@dataclass
class IngestReport:
    """Doc ids (slugs) by outcome; `failed` maps a slug to its error."""

    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        line = (
            f"added {len(self.added)} · updated {len(self.updated)} · "
            f"unchanged {len(self.unchanged)} · removed {len(self.removed)}"
        )
        return line + (f" · failed {len(self.failed)}" if self.failed else "")


def ingest_folder(
    conn: psycopg.Connection, settings: Settings, embeddings: Embeddings
) -> IngestReport:
    """Bring the tenant's documents in line with `settings.corpus_dir`.

    `conn` must be in autocommit mode, so each document gets its own transaction: one failed
    document is rolled back and reported, and the others still go in.
    """
    if not conn.autocommit:
        raise ValueError("ingest_folder needs an autocommit connection (one transaction per doc)")
    tenant = conn.execute(
        "SELECT id, roles FROM tenants WHERE name = %s", (settings.tenant,)
    ).fetchone()
    if tenant is None:
        raise ValueError(f"Tenant {settings.tenant!r} not found; run the migrations first")
    tenant_id, roles = tenant
    stored = dict(
        conn.execute(
            "SELECT slug, content_hash FROM documents WHERE tenant_id = %s", (tenant_id,)
        ).fetchall()
    )

    pages_by_slug: dict[str, list[Page]] = defaultdict(list)
    for page in load_pages(settings.corpus_dir):
        pages_by_slug[page.doc_id].append(page)

    report = IngestReport()
    for slug, pages in sorted(pages_by_slug.items()):
        content_hash = _fingerprint(settings.corpus_dir / pages[0].source)
        if stored.get(slug) == content_hash:
            report.unchanged.append(slug)
            continue
        try:
            _replace_document(conn, settings, embeddings, tenant_id, roles, pages, content_hash)
        except Exception as error:  # report and carry on; the transaction has rolled back
            report.failed[slug] = f"{type(error).__name__}: {error}"
            continue
        (report.updated if slug in stored else report.added).append(slug)

    for slug in sorted(set(stored) - set(pages_by_slug)):
        conn.execute("DELETE FROM documents WHERE tenant_id = %s AND slug = %s", (tenant_id, slug))
        report.removed.append(slug)
    return report


def _fingerprint(path: Path) -> str:
    """SHA-256 of the file's bytes: any change to the file gives a completely different value."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_document(
    conn: psycopg.Connection,
    settings: Settings,
    embeddings: Embeddings,
    tenant_id: str,
    roles: list[str],
    pages: list[Page],
    content_hash: str,
) -> None:
    chunks = chunk_pages(
        pages,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        encoding_name=settings.tokenizer_encoding,
    )
    # Embed before opening the transaction: a slow network call shouldn't hold database locks.
    vectors = embeddings.embed_documents([c.text for c in chunks])

    with conn.transaction():  # all of it, or none of it
        (document_id,) = conn.execute(
            """INSERT INTO documents (tenant_id, slug, source, content_hash, allowed_roles)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (tenant_id, slug) DO UPDATE
                   SET source = EXCLUDED.source, content_hash = EXCLUDED.content_hash,
                       version = documents.version + 1, ingested_at = now()
               RETURNING id""",
            (tenant_id, pages[0].doc_id, pages[0].source, content_hash, roles),
        ).fetchone()
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks (document_id, tenant_id, allowed_roles, page, chunk_index,
                                       content, embedding, embedding_model, content_hash)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [
                    (
                        document_id,
                        tenant_id,
                        roles,
                        chunk.page,
                        int(chunk.id.rsplit(":", 1)[1]),  # "doc_id:page:index"
                        chunk.text,
                        vector,
                        settings.embedding_model,
                        hashlib.sha256(chunk.text.encode()).hexdigest(),
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    embeddings: Embeddings | None = None,
) -> int:
    description = __doc__.split("\n")[0]
    parser = argparse.ArgumentParser(prog="python -m app.ingest", description=description)
    parser.parse_args(argv)
    settings = settings or get_settings()
    if not settings.database_url:
        print("Error: DATABASE_URL is not set (see .env.example).", file=sys.stderr)
        return 1
    embeddings = embeddings or make_embeddings(settings.embedding_model)

    with connect(settings.database_url, autocommit=True) as conn:
        report = ingest_folder(conn, settings, embeddings)

    print(report.summary())
    for slug, error in report.failed.items():
        print(f"  failed {slug}: {error}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
