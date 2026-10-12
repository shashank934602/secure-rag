"""Split pages into token-sized chunks. A chunk never spans two pages."""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.domain import Chunk, Page


def chunk_pages(
    pages: list[Page], *, chunk_size: int, chunk_overlap: int, encoding_name: str
) -> list[Chunk]:
    """Chunk each page separately; ids are 'doc_id:page:index' with index counted per page."""
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=encoding_name, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks: list[Chunk] = []
    for page in pages:
        for index, text in enumerate(splitter.split_text(page.text)):
            chunks.append(
                Chunk(
                    id=f"{page.doc_id}:{page.page}:{index}",
                    doc_id=page.doc_id,
                    source=page.source,
                    page=page.page,
                    text=text,
                )
            )
    return chunks
