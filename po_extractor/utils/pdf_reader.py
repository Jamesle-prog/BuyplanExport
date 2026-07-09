"""pypdfium2 PDF text reader (replaces fitz/PyMuPDF which is not installed)."""
import pypdfium2 as pdfium


def read_pdf_text(pdf_path: str, max_pages: int | None = None) -> str:
    """Return combined text of all pages (or just the first *max_pages*).

    ``max_pages`` exists for format DETECTION, where the identifying
    keywords are on the first page(s) — reading a long PO document in full
    just to classify it was the main cost in the upload screen's
    auto-detect step. Parsing always reads the full document.
    """
    doc = pdfium.PdfDocument(pdf_path)
    try:
        pages = []
        for i, page in enumerate(doc):
            if max_pages is not None and i >= max_pages:
                break
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
        return "\n".join(pages)
    finally:
        doc.close()


def read_pdf_bytes_text(pdf_data: bytes, max_pages: int | None = None) -> str:
    """Like :func:`read_pdf_text` but for in-memory PDF bytes (e.g. a PDF
    attachment extracted from an Outlook .msg)."""
    doc = pdfium.PdfDocument(pdf_data)
    try:
        pages = []
        for i, page in enumerate(doc):
            if max_pages is not None and i >= max_pages:
                break
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
        return "\n".join(pages)
    finally:
        doc.close()


def read_pdf_pages(pdf_path: str) -> list[str]:
    """Return per-page text."""
    doc = pdfium.PdfDocument(pdf_path)
    try:
        result = []
        for page in doc:
            textpage = page.get_textpage()
            result.append(textpage.get_text_range())
        return result
    finally:
        doc.close()
