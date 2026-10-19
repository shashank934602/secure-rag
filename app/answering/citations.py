"""Find `[doc_id:page]` citations in an answer and check them against the retrieved chunks.

Real models also write full-width brackets `【doc_id:page】` and chunk ids `doc_id:page:index`;
both are accepted and reduced to the document and page (ISS-015).
"""

import re

from app.domain import Citation, ScoredChunk

_BRACKET = re.compile(r"[\[【]([^\[\]【】]+)[\]】]")
_REFERENCE = re.compile(r"^\s*([a-z0-9][a-z0-9-]*):(\d+)(?::\d+)?\s*$")


def parse_citations(text: str) -> list[Citation]:
    """Citations in order of first appearance, without duplicates.

    Accepts one or several references per bracket: `[a:1]`, `[a:1, b:2]`, `[a:1; b:2]`.
    A bracket counts only if every part of it is a reference, so ordinary brackets are ignored.
    """
    found: list[Citation] = []
    for group in _BRACKET.findall(text):
        matches = [_REFERENCE.match(part) for part in re.split(r"[,;]", group)]
        if not all(matches):
            continue
        for m in matches:
            citation = Citation(doc_id=m.group(1), page=int(m.group(2)))
            if citation not in found:
                found.append(citation)
    return found


def all_citations_retrieved(citations: list[Citation], retrieved: list[ScoredChunk]) -> bool:
    """True if every citation points to the page of at least one retrieved chunk."""
    pages = {(r.chunk.doc_id, r.chunk.page) for r in retrieved}
    return all((c.doc_id, c.page) in pages for c in citations)
