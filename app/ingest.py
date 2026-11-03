"""Ingest a folder of documents into Postgres for one tenant (spec 02 step 3; spec 04 D3).

    uv run python -m app.ingest                                  # data/sample → Aldermoor
    uv run python -m app.ingest --tenant "Northgate Haulage" --folder data/tenants/northgate
    uv run python -m app.ingest --folder data/tenants/aldermoor-hr --roles hr

`--roles` is the audience of *new* documents (default: employee); change an existing document's
audience with PATCH /v1/documents/{doc_id}/acl. Each folder is its own collection: ingesting one
folder never removes documents that came from another.

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
from app.db import connect, tenant_scope
from app.domain import Page
from app.guards.injection import InjectionClassifier, injection_classifier
from app.guards.pii import mask
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
    quarantined: list[str] = field(default_factory=list)  # also in added/updated, but inactive

    def summary(self) -> str:
        line = (
            f"added {len(self.added)} · updated {len(self.updated)} · "
            f"unchanged {len(self.unchanged)} · removed {len(self.removed)}"
        )
        line += f" · quarantined {len(self.quarantined)}" if self.quarantined else ""
        return line + (f" · failed {len(self.failed)}" if self.failed else "")


def ingest_folder(
    conn: psycopg.Connection,
    settings: Settings,
    embeddings: Embeddings,
    *,
    allowed_roles: list[str] | None = None,
    collection: str | None = None,
    classifier: InjectionClassifier | None = None,
) -> IngestReport:
    """Bring `settings.tenant`'s documents from `settings.corpus_dir` up to date.

    `conn` must be in autocommit mode, so each document gets its own transaction: one failed
    document is rolled back and reported, and the others still go in. Every write runs in the
    tenant's scope, so row-level security rejects a row for any other tenant.
    """
    if not conn.autocommit:
        raise ValueError("ingest_folder needs an autocommit connection (one transaction per doc)")
    tenant = conn.execute(
        "SELECT id, roles FROM tenants WHERE name = %s", (settings.tenant,)
    ).fetchone()
    if tenant is None:
        raise ValueError(f"Tenant {settings.tenant!r} not found; run the migrations first")
    tenant_id, tenant_roles = tenant
    roles = allowed_roles or ["employee"]
    if not set(roles) <= set(tenant_roles):
        raise ValueError(f"Roles {roles} are not all roles of {settings.tenant!r}: {tenant_roles}")
    collection = collection or settings.corpus_dir.name
    with tenant_scope(conn, tenant_id):
        stored = dict(
            conn.execute(
                "SELECT slug, content_hash FROM documents WHERE tenant_id = %s AND collection = %s",
                (tenant_id, collection),
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
            flagged = _replace_document(
                conn,
                settings,
                embeddings,
                classifier,
                tenant_id,
                roles,
                collection,
                pages,
                content_hash,
            )
        except Exception as error:  # report and carry on; the transaction has rolled back
            report.failed[slug] = f"{type(error).__name__}: {error}"
            continue
        (report.updated if slug in stored else report.added).append(slug)
        if flagged:
            report.quarantined.append(slug)

    for slug in sorted(set(stored) - set(pages_by_slug)):
        with tenant_scope(conn, tenant_id):
            conn.execute(
                "DELETE FROM documents WHERE tenant_id = %s AND slug = %s", (tenant_id, slug)
            )
        report.removed.append(slug)
    return report


def _fingerprint(path: Path) -> str:
    """SHA-256 of the file's bytes: any change to the file gives a completely different value."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace_document(
    conn: psycopg.Connection,
    settings: Settings,
    embeddings: Embeddings,
    classifier: InjectionClassifier | None,
    tenant_id: str,
    roles: list[str],
    collection: str,
    pages: list[Page],
    content_hash: str,
) -> bool:
    """Store the document; returns True if it was quarantined (an injection scan hit)."""
    chunks = chunk_pages(
        pages,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        encoding_name=settings.tokenizer_encoding,
    )
    # Scan and embed before opening the transaction: slow work shouldn't hold database locks.
    pii = [mask(c.text)[1] for c in chunks]  # detected types only; the text stays raw (ADR-0004)
    scores = [classifier.score(c.text) for c in chunks] if classifier else [None] * len(chunks)
    flagged = any(s is not None and s >= settings.injection_threshold for s in scores)
    vectors = embeddings.embed_documents([c.text for c in chunks])

    with tenant_scope(conn, tenant_id):  # all of it, or none of it, as this tenant
        # `roles` applies only to a new document: an existing one keeps its audience (it may have
        # been changed through the API), and its chunks copy it from the document (ADR-0002).
        (document_id, roles) = conn.execute(
            """INSERT INTO documents
                   (tenant_id, slug, source, content_hash, allowed_roles, collection, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (tenant_id, slug) DO UPDATE
                   SET source = EXCLUDED.source, content_hash = EXCLUDED.content_hash,
                       status = EXCLUDED.status, version = documents.version + 1,
                       ingested_at = now()
               RETURNING id, allowed_roles""",
            (
                tenant_id,
                pages[0].doc_id,
                pages[0].source,
                content_hash,
                roles,
                collection,
                "quarantined" if flagged else "active",
            ),
        ).fetchone()
        conn.execute("DELETE FROM chunks WHERE document_id = %s", (document_id,))
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO chunks (document_id, tenant_id, allowed_roles, page, chunk_index,
                                       content, embedding, embedding_model, content_hash,
                                       pii_types, injection_score, is_active)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
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
                        kinds,
                        score,
                        not flagged,  # a quarantined document's chunks are never searched
                    )
                    for chunk, vector, kinds, score in zip(
                        chunks, vectors, pii, scores, strict=True
                    )
                ],
            )
    return flagged


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    embeddings: Embeddings | None = None,
) -> int:
    description = __doc__.split("\n")[0]
    parser = argparse.ArgumentParser(prog="python -m app.ingest", description=description)
    parser.add_argument("--tenant", help="tenant name (default: settings.tenant, Aldermoor)")
    parser.add_argument("--folder", type=Path, help="folder to ingest (default: data/sample)")
    parser.add_argument("--roles", help="audience of new documents, comma-separated (employee)")
    parser.add_argument("--collection", help="collection name (default: the folder's name)")
    args = parser.parse_args(argv)
    settings = settings or get_settings()
    overrides = {"tenant": args.tenant, "corpus_dir": args.folder}
    settings = settings.model_copy(update={k: v for k, v in overrides.items() if v is not None})
    roles = args.roles.split(",") if args.roles else None
    if not settings.database_url:
        print("Error: DATABASE_URL is not set (see .env.example).", file=sys.stderr)
        return 1
    embeddings = embeddings or make_embeddings(settings.embedding_model)

    with connect(settings.database_url, autocommit=True) as conn:
        classifier = injection_classifier(settings) if settings.input_guard else None
        report = ingest_folder(
            conn,
            settings,
            embeddings,
            allowed_roles=roles,
            collection=args.collection,
            classifier=classifier,
        )

    print(report.summary())
    for slug in report.quarantined:
        print(f"  quarantined {slug}: possible prompt injection; its chunks are not searchable")
    for slug, error in report.failed.items():
        print(f"  failed {slug}: {error}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
