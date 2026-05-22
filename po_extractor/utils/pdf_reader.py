"""pypdfium2 PDF text reader (replaces fitz/PyMuPDF which is not installed)."""
import pypdfium2 as pdfium


def read_pdf_text(pdf_path: str) -> str:
    """Return combined text of all pages."""
    doc = pdfium.PdfDocument(pdf_path)
    try:
        pages = []
        for page in doc:
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
