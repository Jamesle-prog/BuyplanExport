"""PyMuPDF wrapper."""
import fitz


def read_pdf_text(pdf_path: str) -> str:
    """Return combined text of all pages."""
    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def read_pdf_pages(pdf_path: str) -> list[str]:
    """Return per-page text."""
    doc = fitz.open(pdf_path)
    try:
        return [page.get_text() for page in doc]
    finally:
        doc.close()
