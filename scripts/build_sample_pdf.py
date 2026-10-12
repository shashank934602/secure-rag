"""Build the sample PDF in data/sample/ from its Markdown source.

The source lives outside data/sample/ so the loader only sees the PDF.
Each `<!-- pagebreak -->` line starts a new PDF page, so golden-set page
numbers stay stable.

    uv run python scripts/build_sample_pdf.py
"""

from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "sample_sources" / "vendor-contract-swiftparts.md"
TARGET = ROOT / "data" / "sample" / "vendor-contract-swiftparts.pdf"
PAGE_BREAK = "<!-- pagebreak -->"


def build(source: Path, target: Path) -> int:
    pdf = FPDF(format="A4")
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=False)
    pdf.set_creation_date(datetime(2025, 2, 14, tzinfo=timezone.utc))  # reproducible output
    pdf.add_page()

    for line in source.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text == PAGE_BREAK:
            pdf.add_page()
        elif text.startswith("# "):
            pdf.set_font("Helvetica", "B", 16)
            pdf.multi_cell(0, 9, text[2:], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        elif text.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, text[3:], new_x="LMARGIN", new_y="NEXT")
        elif text.startswith("- "):
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, "- " + text[2:], new_x="LMARGIN", new_y="NEXT")
        elif text:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.ln(2)

        if pdf.get_y() > pdf.h - 20:
            raise ValueError(f"Content overflows page {pdf.page_no()}; add a page break earlier.")

    target.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(target))
    return pdf.page_no()


if __name__ == "__main__":
    pages = build(SOURCE, TARGET)
    print(f"Wrote {TARGET.relative_to(ROOT)} ({pages} pages)")
