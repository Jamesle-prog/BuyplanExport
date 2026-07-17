"""Regression test for ui/fabric_db/import_section.py (Fix 5).

The temp file written for the uploaded .xlsx must be removed even when the
store call raises — previously os.unlink() sat after the call with no
try/finally, so a raising import leaked the temp file forever. (The UI now
stages uploads for review via store.propose_import rather than importing
directly; the temp-file guarantee is the same.)
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
    def propose_import(self, path, source_file_name=None,
                       proposed_by=None, clear_first=False):
        raise RuntimeError("boom — simulated parse failure")


class _OkStore:
    def propose_import(self, path, source_file_name=None,
                       proposed_by=None, clear_first=False):
        return {"pending_id": 1, "row_count": 1, "skipped": 0,
                "diff_added": 1, "diff_removed": 0, "diff_changed": 0,
                "warnings": [], "high_risk": False,
                "unmatched_headers": [], "col_map": {}}


def _track_created_paths(monkeypatch):
    created: list[str] = []
    real_ctor = isec.tempfile.NamedTemporaryFile

    def _wrapped(*a, **k):
        f = real_ctor(*a, **k)
        created.append(f.name)
        return f

    monkeypatch.setattr(isec.tempfile, "NamedTemporaryFile", _wrapped)
    return created


def test_temp_file_removed_when_propose_raises(monkeypatch):
    created = _track_created_paths(monkeypatch)

    # _fabric_db_do_propose catches everything internally (calls st.error) —
    # it must not raise, and the temp file must still be gone afterwards.
    isec._fabric_db_do_propose(_RaisingStore(), _FakeUpload())

    assert len(created) == 1
    assert not os.path.exists(created[0]), f"leaked temp file: {created[0]}"


def test_temp_file_removed_on_successful_propose(monkeypatch):
    created = _track_created_paths(monkeypatch)
    monkeypatch.setattr(isec.st, "rerun", lambda: None)  # avoid bare-mode no-op surprises

    isec._fabric_db_do_propose(_OkStore(), _FakeUpload())

    assert len(created) == 1
    assert not os.path.exists(created[0]), f"leaked temp file: {created[0]}"
