"""PDFium is not thread-safe — concurrent reads must be serialised by a lock,
or the whole interpreter segfaults (which crashed the Streamlit server when the
upload pipeline parsed files across a thread pool). This guards the lock."""
from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

import pypdfium2 as pdfium

from po_extractor.utils import pdf_reader
from po_extractor.utils.pdf_reader import read_pdf_bytes_text, _PDFIUM_LOCK


def _minimal_pdf_bytes() -> bytes:
    doc = pdfium.PdfDocument.new()
    doc.new_page(200, 200)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_lock_exists():
    import threading
    assert isinstance(_PDFIUM_LOCK, type(threading.Lock()))


def test_concurrent_reads_do_not_crash():
    data = _minimal_pdf_bytes()
    # 6 workers × many reads — before the lock this could segfault the process
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda _: read_pdf_bytes_text(data), range(60)))
    assert len(results) == 60          # all completed, no crash
    assert all(isinstance(r, str) for r in results)
