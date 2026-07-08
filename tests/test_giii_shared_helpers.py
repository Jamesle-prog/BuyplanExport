"""Tests for the shared GIII extraction helpers (ui/giii/_shared.py)."""
from __future__ import annotations

import io


class _FakeUpload:
    """Minimal stand-in for a Streamlit UploadedFile."""
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
        self.size = len(data)

    def getbuffer(self):
        return memoryview(self._data)


def test_iter_pdf_payloads_passes_bare_pdfs_through():
    from ui.giii._shared import iter_pdf_payloads
    files = [_FakeUpload("fax_a.PDF", b"%PDF-1.4 aaa"),
             _FakeUpload("fax_b.pdf", b"%PDF-1.4 bbb")]
    out = list(iter_pdf_payloads(files))
    assert out == [("fax_a.PDF", b"%PDF-1.4 aaa", ""),
                   ("fax_b.pdf", b"%PDF-1.4 bbb", "")]


def test_fax_size_order_matches_historical_columns():
    from ui.giii._shared import FAX_SIZE_ORDER
    # Column order is part of the generated workbooks' layout — lock it.
    assert FAX_SIZE_ORDER == ['XS', 'S', 'M', 'L', 'XL', 'XXL', '1X', '2X', '3X']


def test_shared_palette_matches_historical_colors():
    from ui.giii import _shared as sh
    assert sh.XL_NAVY == 'FF1F3864'
    assert sh.XL_WHITE == 'FFFFFFFF'
    assert sh.XL_YELLOW == 'FFFFF2CC'
    assert sh.XL_GREY == 'FFD9D9D9'
    assert sh.XL_LTBLUE == 'FFDEEAF1'
    assert sh.XL_GREEN == 'FFE2EFDA'


def test_extraction_modules_share_the_constants():
    from ui.giii import _shared as sh
    from ui.giii import msg_extraction, kl_extraction, tk_eu_extraction
    for mod in (msg_extraction, kl_extraction, tk_eu_extraction):
        assert mod._SIZE_ORDER is sh.FAX_SIZE_ORDER
        assert mod._NAVY == sh.XL_NAVY
