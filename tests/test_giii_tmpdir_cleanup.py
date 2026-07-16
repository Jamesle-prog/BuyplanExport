"""Regression tests: GIII pipeline entry points must always remove their
tempfile.mkdtemp() scratch directories, even on the "nothing to process"
early-return path (previously the cleanup only ran at the very end of the
happy path with no try/finally).
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.giii.extraction as ext
import ui.giii.excel_extraction as xext
import ui.giii.reference as ref


class _FakeStatus:
    """Minimal stand-in for the object `with st.status(...) as status:` binds
    outside of a real Streamlit app context (real st.status returns None
    there, so `status.update(...)` would crash before reaching our code)."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def update(self, *a, **k):
        pass


def _track_mkdtemp(monkeypatch, module):
    """Patch module.tempfile.mkdtemp to record every directory it creates."""
    created: list[str] = []
    real_mkdtemp = module.tempfile.mkdtemp

    def _wrapped(*a, **k):
        d = real_mkdtemp(*a, **k)
        created.append(d)
        return d

    monkeypatch.setattr(module.tempfile, "mkdtemp", _wrapped)
    return created


def test_run_extraction_cleans_up_on_no_valid_pos(monkeypatch):
    """Fix 2: _run_extraction must remove tmpdir/out_dir even when it bails
    out early on the 'no valid POs could be parsed' branch."""
    created = _track_mkdtemp(monkeypatch, ext)
    monkeypatch.setattr(ext.st, "status", lambda *a, **k: _FakeStatus())

    ext._run_extraction([], mask_prices=False, company="")

    assert len(created) == 2
    for d in created:
        assert not os.path.isdir(d), f"leaked temp dir: {d}"


def test_run_smart_processing_cleans_up_when_no_groups(monkeypatch):
    """Fix 1: _run_smart_processing's out_dir must be removed even when
    there is nothing to group/process."""
    created = _track_mkdtemp(monkeypatch, ext)
    monkeypatch.setattr(ext.st, "status", lambda *a, **k: _FakeStatus())

    ext._run_smart_processing([], {}, mask_prices=False)

    assert len(created) == 1
    assert not os.path.isdir(created[0]), f"leaked temp dir: {created[0]}"


def test_run_excel_extraction_cleans_up_on_empty_input(monkeypatch):
    """Fix 3: _run_excel_extraction must remove tmpdir/out_dir even when it
    bails out early on the 'no data found' branch."""
    created = _track_mkdtemp(monkeypatch, xext)
    monkeypatch.setattr(xext.st, "status", lambda *a, **k: _FakeStatus())

    xext._run_excel_extraction([], sheet_name="1.1.PO_Client")

    assert len(created) == 2
    for d in created:
        assert not os.path.isdir(d), f"leaked temp dir: {d}"


class _FakeUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getbuffer(self):
        return self._data


def test_run_giii_mapping_import_cleans_up_on_parse_failure(monkeypatch):
    """Fix 4: _run_giii_mapping_import's tmpdir must be removed even when
    parsing the uploaded file raises."""
    created = _track_mkdtemp(monkeypatch, ref)
    monkeypatch.setattr(
        ref, "_parse_fabric_mapping_file",
        lambda path: (_ for _ in ()).throw(ValueError("corrupt workbook")),
    )

    ref._run_giii_mapping_import(_FakeUpload("mapping.xlsx", b"not a real xlsx"))

    assert len(created) == 1
    assert not os.path.isdir(created[0]), f"leaked temp dir: {created[0]}"


def test_run_giii_mapping_import_cleans_up_on_success(monkeypatch):
    """The tmpdir must also be removed on the normal (non-exception) path."""
    created = _track_mkdtemp(monkeypatch, ref)
    monkeypatch.setattr(ref, "_parse_fabric_mapping_file", lambda path: {})

    ref._run_giii_mapping_import(_FakeUpload("mapping.xlsx", b"anything"), dry_run=True)

    assert len(created) == 1
    assert not os.path.isdir(created[0]), f"leaked temp dir: {created[0]}"
