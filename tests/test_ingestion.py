import json
from pathlib import Path

import pytest
import tiktoken
from fpdf import FPDF

from app.ingestion.chunking import chunk_pages
from app.ingestion.loaders import UnsupportedFileError, load_pages

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "data" / "sample"
GOLDEN = ROOT / "eval" / "datasets" / "golden.jsonl"
ENCODING = "cl100k_base"


def write_pdf(path: Path, page_texts: list[str]) -> None:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    for text in page_texts:
        pdf.add_page()
        pdf.multi_cell(0, 6, text)
    pdf.output(str(path))


# --- loading ---------------------------------------------------------------


def test_markdown_file_is_one_page_numbered_1(tmp_path: Path) -> None:
    (tmp_path / "Leave Policy.md").write_text("# Leave\n\n25 days.")

    [page] = load_pages(tmp_path)

    assert page.doc_id == "leave-policy"
    assert page.source == "Leave Policy.md"
    assert page.page == 1
    assert "25 days." in page.text


def test_pdf_gives_one_page_per_pdf_page_numbered_from_1(tmp_path: Path) -> None:
    write_pdf(tmp_path / "contract.pdf", ["First page text.", "Second page text."])

    pages = load_pages(tmp_path)

    assert [(p.doc_id, p.page) for p in pages] == [("contract", 1), ("contract", 2)]
    assert "Second page text." in pages[1].text


def test_hidden_files_are_ignored(tmp_path: Path) -> None:
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x01")
    (tmp_path / "a.md").write_text("A")

    assert [p.doc_id for p in load_pages(tmp_path)] == ["a"]


def test_unsupported_file_type_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello")

    with pytest.raises(UnsupportedFileError):
        load_pages(tmp_path)


def test_two_files_with_the_same_doc_id_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "policy.md").write_text("A")
    write_pdf(tmp_path / "policy.pdf", ["B"])

    with pytest.raises(ValueError, match="policy"):
        load_pages(tmp_path)


def test_pdf_page_without_text_is_skipped(tmp_path: Path) -> None:
    write_pdf(tmp_path / "scan.pdf", ["Has text.", ""])

    assert [p.page for p in load_pages(tmp_path)] == [1]


# --- chunking --------------------------------------------------------------


def test_chunk_ids_are_doc_id_page_index(tmp_path: Path) -> None:
    long_text = "\n\n".join(f"Paragraph {i}. " + "word " * 60 for i in range(10))
    (tmp_path / "handbook.md").write_text(long_text)

    chunks = chunk_pages(
        load_pages(tmp_path), chunk_size=100, chunk_overlap=10, encoding_name=ENCODING
    )

    assert len(chunks) > 1
    assert [c.id for c in chunks] == [f"handbook:1:{i}" for i in range(len(chunks))]
    assert all(c.doc_id == "handbook" and c.page == 1 for c in chunks)


def test_chunks_respect_the_token_limit(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("\n\n".join(f"sentence number {i}. " * 8 for i in range(40)))
    enc = tiktoken.get_encoding(ENCODING)

    chunks = chunk_pages(
        load_pages(tmp_path), chunk_size=80, chunk_overlap=10, encoding_name=ENCODING
    )

    assert all(len(enc.encode(c.text)) <= 80 for c in chunks)


def test_a_chunk_never_spans_two_pdf_pages(tmp_path: Path) -> None:
    write_pdf(tmp_path / "contract.pdf", ["Alpha clause.", "Beta clause."])

    chunks = chunk_pages(
        load_pages(tmp_path), chunk_size=400, chunk_overlap=50, encoding_name=ENCODING
    )

    assert [(c.id, c.text) for c in chunks] == [
        ("contract:1:0", "Alpha clause."),
        ("contract:2:0", "Beta clause."),
    ]


# --- the real sample corpus ------------------------------------------------


def test_every_golden_source_page_has_chunks() -> None:
    chunks = chunk_pages(
        load_pages(SAMPLE_DIR), chunk_size=400, chunk_overlap=50, encoding_name=ENCODING
    )
    chunk_pages_seen = {f"{c.doc_id}:{c.page}" for c in chunks}

    expected = {
        source
        for line in GOLDEN.read_text().splitlines()
        for source in json.loads(line)["expected_sources"]
    }

    assert expected <= chunk_pages_seen
