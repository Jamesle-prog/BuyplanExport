"""Regression test for ui/fabric_db/import_section.py (Fix 5).

The temp file written for the uploaded .xlsx must be removed even when
store.import_from_xlsx() raises — previously os.unlink() sat after the call
with no try/finally, so a raising import leaked the temp file forever.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.fabric_db.import_section as isec


class _FakeUpload:
    name = "面料统计表.xlsx"

    def getbuffer(self):
        return b"not a real workbook, just bytes"


class _RaisingStore:
    def import_from_xlsx(self, path, source_file_name=None):
        raise RuntimeError("boom — simulated import failure")


class _OkStore:
    def import_from_xlsx(self, path, source_file_name=None):
        return {"inserted": 1, "updated": 0, "skipped": 0, "total": 1}


def _track_created_paths(monkeypatch):
    created: list[str] = []
    real_ctor = isec.tempfile.NamedTemporaryFile

    def _wrapped(*a, **k):
        f = real_ctor(*a, **k)
        created.append(f.name)
        return f

    monkeypatch.setattr(isec.tempfile, "NamedTemporaryFile", _wrapped)
    return created


def test_temp_file_removed_when_import_raises(monkeypatch):
    created = _track_created_paths(monkeypatch)

    # _fabric_db_do_import catches everything internally (calls st.error) —
    # it must not raise, and the temp file must still be gone afterwards.
    isec._fabric_db_do_import(_RaisingStore(), _FakeUpload())

    assert len(created) == 1
    assert not os.path.exists(created[0]), f"leaked temp file: {created[0]}"


def test_temp_file_removed_on_successful_import(monkeypatch):
    created = _track_created_paths(monkeypatch)
    monkeypatch.setattr(isec.st, "rerun", lambda: None)  # avoid bare-mode no-op surprises

    isec._fabric_db_do_import(_OkStore(), _FakeUpload())

    assert len(created) == 1
    assert not os.path.exists(created[0]), f"leaked temp file: {created[0]}"
