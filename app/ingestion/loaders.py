"""Read every document in a folder into pages with a doc id and 1-based page numbers."""

import re
from pathlib import Path

from pypdf import PdfReader

from app.domain import Page


class UnsupportedFileError(ValueError):
    """A file in the corpus folder has a type we cannot load."""


def load_pages(folder: Path) -> list[Page]:
    """Load Markdown (one page) and PDF (one page per PDF page) files, sorted by filename.

    Hidden files are ignored. Any other file type, or two files with the same doc id,
    is an error rather than something to skip silently.
    """
    pages: list[Page] = []
    seen: dict[str, str] = {}
    for path in sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".")):
        doc_id = doc_id_for(path)
        if doc_id in seen:
            raise ValueError(f"{path.name} and {seen[doc_id]} both have doc id {doc_id!r}")
        seen[doc_id] = path.name
        pages.extend(_load_file(path, doc_id))
    return pages


def doc_id_for(path: Path) -> str:
    """Slug of the filename stem: 'Leave Policy.md' -> 'leave-policy'."""
    return re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")


def _load_file(path: Path, doc_id: str) -> list[Page]:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return [
            Page(doc_id=doc_id, source=path.name, page=1, text=path.read_text(encoding="utf-8"))
        ]
    if suffix == ".pdf":
        pages = []
        for number, pdf_page in enumerate(PdfReader(path).pages, start=1):
            text = pdf_page.extract_text() or ""
            if text.strip():
                pages.append(Page(doc_id=doc_id, source=path.name, page=number, text=text))
        return pages
    raise UnsupportedFileError(f"Cannot load {path.name}: unsupported file type {suffix!r}")
