"""Regression tests for ui/giii/excel_extraction.py's processing-log building.

Focus: every log line built from uploaded-file content (cell values,
filenames, exception text) must be HTML-escaped before being appended to the
``log`` list, because ``show_processing_log()`` (ui/shared.py) renders that
list with ``st.markdown(line, unsafe_allow_html=True)``. Un-escaped values
would let a malicious cell/filename execute as live HTML (stored XSS) in the
viewer's browser.

These tests exercise the real log-building code paths in
``_log_photo_matches``, ``_process_excel_group`` and ``_run_excel_extraction``
with the heavy external dependencies (parsers, exporters, DB stores,
Streamlit chrome) monkeypatched out, consistent with this repo's convention
of not unit-testing Streamlit rendering itself (see test_progress_mapping_view.py).
"""
from __future__ import annotations

import contextlib

import pandas as pd
import pytest


class _FakeUpload:
    """Minimal stand-in for a Streamlit UploadedFile."""
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getbuffer(self):
        return memoryview(self._data)


# ---------------------------------------------------------------------------
# _log_photo_matches — "no photo" style-name list
# ---------------------------------------------------------------------------

def test_log_photo_matches_escapes_style_names_with_no_photo():
    from ui.giii.excel_extraction import _log_photo_matches

    df = pd.DataFrame({
        "Main Supplier Config SKU": ["<img src=x onerror=alert(1)>"],
    })
    log: list[str] = []
    _log_photo_matches(df, {"some_photo.png": b"x"}, log)

    joined = "\n".join(log)
    assert "<img src=x onerror=alert(1)>" not in joined
    assert "&lt;img src=x onerror=alert(1)&gt;" in joined


def test_log_photo_matches_no_photo_map_is_not_html():
    """The 'no photos loaded' line is app-authored text, not a template that
    needs escaping -- guards against a future refactor breaking this branch."""
    from ui.giii.excel_extraction import _log_photo_matches

    df = pd.DataFrame({"Main Supplier Config SKU": ["STY1"]})
    log: list[str] = []
    _log_photo_matches(df, {}, log)
    assert log == ["📷 No photos loaded from image folder"]


# ---------------------------------------------------------------------------
# _process_excel_group — skipped/source/conflict/repeat lines
# ---------------------------------------------------------------------------

def test_process_excel_group_escapes_html_in_log(monkeypatch, tmp_path):
    from ui.giii import excel_extraction as ee

    class _FakeResult:
        def __init__(self):
            self.df = pd.DataFrame({
                "Main Supplier Config SKU": ["STY1"],
                "_source_file": ["po.xlsx"],
            })
            self.skipped_files = ["<script>alert('skip')</script>.xlsx: boom"]
            self.source_files = ["<b>evil</b>.xlsx"]
            self.conflicts = ["Qty mismatch for <i>STY1</i>"]
            self.repeat_orders = {}

    bp_path = tmp_path / "bp.xlsx"
    bp_path.write_bytes(b"fake")

    monkeypatch.setattr(ee, "get_company", lambda name: {})
    monkeypatch.setattr(ee, "combine_excel_files", lambda paths, sheet_name: _FakeResult())
    monkeypatch.setattr(
        ee, "repeat_order_summary",
        lambda result: ["Style '<u>repeat</u>' appears in 2 PO(s): PO1, PO2"],
    )
    monkeypatch.setattr(ee, "_save_fabric_parts_from_df", lambda df, source: None)
    monkeypatch.setattr(
        ee, "get_color_translation_store",
        lambda: (_ for _ in ()).throw(RuntimeError("no db in test")),
    )
    monkeypatch.setattr(ee, "export_hhp_buyplan", lambda *a, **k: str(bp_path))
    monkeypatch.setattr(ee, "export_hhp_template_p", lambda *a, **k: [])

    log: list[str] = []
    out = ee._process_excel_group("GIII", [], str(tmp_path), {}, log)

    assert out is not None
    joined = "\n".join(log)
    # No raw tag survives unescaped.
    assert "<script>alert" not in joined
    assert "<b>evil</b>" not in joined
    assert "<i>STY1</i>" not in joined
    assert "<u>repeat</u>" not in joined
    # Escaped forms are present.
    assert "&lt;script&gt;alert(&#x27;skip&#x27;)&lt;/script&gt;" in joined
    assert "&lt;b&gt;evil&lt;/b&gt;" in joined
    assert "&lt;i&gt;STY1&lt;/i&gt;" in joined
    assert "&lt;u&gt;repeat&lt;/u&gt;" in joined
    # The app's own <span> colour-coding markup must survive untouched.
    assert '<span style="color:#dc3545">' in joined
    assert '<span style="color:#198754">' in joined
    assert '<span style="color:#b08800">' in joined


# ---------------------------------------------------------------------------
# _run_excel_extraction — full pipeline, including the colour-cleanup log
# ---------------------------------------------------------------------------

def test_run_excel_extraction_escapes_html_in_all_log_sites(monkeypatch, tmp_path):
    import streamlit as st
    from ui.giii import excel_extraction as ee

    class _FakeProgressFile:
        def getvalue(self):
            return b"fake-bytes"

    class _FakeProgressLookup:
        def __init__(self, data=None):
            pass

        def __len__(self):
            return 1

        def get_record(self, *a, **kw):
            return None

    class _FakeResult:
        def __init__(self):
            self.df = pd.DataFrame({
                "Main Supplier Config SKU": ["STY1"],
                "Main Supplier Color Description": ["<img src=x onerror=alert(1)>"],
                "Purchase Order Number": ["PO1"],
            })
            self.skipped_files = ["<script>alert('skip')</script>.xlsx: boom"]
            self.source_files = ["<b>evil</b>.xlsx"]
            self.conflicts = ["Qty mismatch for <i>STY1</i>"]
            self.repeat_orders = {}

    @contextlib.contextmanager
    def _fake_status(*a, **kw):
        class _S:
            def update(self, **kw):
                pass
        yield _S()

    bp_path = tmp_path / "bp.xlsx"
    bp_path.write_bytes(b"fake")

    monkeypatch.setattr(ee.st, "status", _fake_status)
    monkeypatch.setattr(ee, "combine_excel_files", lambda paths, sheet_name: _FakeResult())
    monkeypatch.setattr(
        ee, "repeat_order_summary",
        lambda result: ["Style '<u>repeat</u>' appears in 2 PO(s): PO1, PO2"],
    )
    monkeypatch.setattr(ee, "_save_fabric_parts_from_df", lambda df, source: None)
    monkeypatch.setattr(
        ee, "get_color_translation_store",
        lambda: (_ for _ in ()).throw(RuntimeError("no db in test")),
    )
    monkeypatch.setattr(ee, "export_hhp_buyplan", lambda *a, **k: str(bp_path))
    monkeypatch.setattr(ee, "export_hhp_template_p", lambda *a, **k: [])
    monkeypatch.setattr("ui.shared.images_dir", lambda key: "")
    monkeypatch.setattr("ui.shared.load_photo_map_from_dir", lambda d: {})
    monkeypatch.setattr("po_extractor.lookups.ProgressLookup", _FakeProgressLookup)

    ee._run_excel_extraction(
        [_FakeUpload("po.xlsx", b"data")],
        sheet_name="1.1.PO_Client",
        progress_file=_FakeProgressFile(),
    )

    log = st.session_state.excel_log
    joined = "\n".join(log)

    assert "<script>alert" not in joined
    assert "<b>evil</b>" not in joined
    assert "<i>STY1</i>" not in joined
    assert "<u>repeat</u>" not in joined
    assert "<img src=x onerror=alert(1)>" not in joined

    assert "&lt;script&gt;alert(&#x27;skip&#x27;)&lt;/script&gt;" in joined
    assert "&lt;b&gt;evil&lt;/b&gt;" in joined
    assert "&lt;i&gt;STY1&lt;/i&gt;" in joined
    assert "&lt;u&gt;repeat&lt;/u&gt;" in joined
    assert "&lt;img src=x onerror=alert(1)&gt;" in joined   # cleanup_lines (raw colour)

    # The app's own <span> colour-coding markup must survive untouched.
    assert '<span style="color:#dc3545">' in joined
