"""pypdfium2 PDF text reader (replaces fitz/PyMuPDF which is not installed).

PDFium is **not thread-safe** — concurrent access from multiple threads
segfaults the whole interpreter (no Python traceback), which crashed the
Streamlit server when the upload pipeline parsed files across a thread pool.
Every pdfium operation here runs under a single process-wide lock. Text
extraction is fast (~ms/page), so serialising it costs nothing while the slow
per-file AI network calls still run concurrently (they hold no pdfium state).
"""
import threading

import pypdfium2 as pdfium

_PDFIUM_LOCK = threading.Lock()


def read_pdf_text(pdf_path: str, max_pages: int | None = None) -> str:
    """Return combined text of all pages (or just the first *max_pages*).

    ``max_pages`` exists for format DETECTION, where the identifying
    keywords are on the first page(s) — reading a long PO document in full
    just to classify it was the main cost in the upload screen's
    auto-detect step. Parsing always reads the full document.
    """
    with _PDFIUM_LOCK:
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
    with _PDFIUM_LOCK:
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
    with _PDFIUM_LOCK:
        doc = pdfium.PdfDocument(pdf_path)
        try:
            result = []
            for page in doc:
                textpage = page.get_textpage()
                result.append(textpage.get_text_range())
            return result
        finally:
            doc.close()
