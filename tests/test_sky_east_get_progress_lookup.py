"""Regression test for ui/sky_east/_shared.py's ``get_progress_lookup``.

A DB error from ``load_progress_records`` used to propagate unhandled,
crashing both Buy Plan generation (ui/sky_east/processing.py) and the
Missing Fields lookup (ui/sky_east/_missing_compute.py), both of which call
this function. It must instead degrade to ``None`` -- the same sentinel
already used when ``source`` resolves to nothing -- like the sibling
upload-file branch a few lines above it that already has its own try/except.
"""
from __future__ import annotations

import streamlit as st


def test_get_progress_lookup_returns_none_when_store_raises(monkeypatch):
    from ui.sky_east._shared import get_progress_lookup
    from ui.session_keys import SK

    st.session_state.pop(SK.SE_PROGRESS_LKUP, None)

    class _BoomStore:
        def load_progress_records(self, source):
            raise RuntimeError("db is locked")

    monkeypatch.setattr("ui.stores.get_store", lambda: _BoomStore())

    assert get_progress_lookup("sky_east") is None


def test_get_progress_lookup_returns_none_when_no_records(monkeypatch):
    from ui.sky_east._shared import get_progress_lookup
    from ui.session_keys import SK

    st.session_state.pop(SK.SE_PROGRESS_LKUP, None)

    class _EmptyStore:
        def load_progress_records(self, source):
            return []

    monkeypatch.setattr("ui.stores.get_store", lambda: _EmptyStore())

    assert get_progress_lookup("sky_east") is None


def test_get_progress_lookup_session_upload_takes_precedence(monkeypatch):
    """An ad-hoc session-uploaded lookup must win, without ever touching the
    store -- confirms the try/except added around the DB path doesn't
    accidentally get triggered on this branch."""
    from ui.sky_east._shared import get_progress_lookup
    from ui.session_keys import SK

    sentinel = object()
    st.session_state[SK.SE_PROGRESS_LKUP] = sentinel
    try:
        def _boom():
            raise AssertionError("store must not be consulted when a session upload exists")
        monkeypatch.setattr("ui.stores.get_store", _boom)

        assert get_progress_lookup("sky_east") is sentinel
    finally:
        st.session_state.pop(SK.SE_PROGRESS_LKUP, None)


def test_get_progress_lookup_builds_from_store_records(monkeypatch):
    """Happy path: non-empty records are handed straight to
    ``ProgressLookup.from_records`` -- confirms the new try/except added for
    Fix 2 only swallows the DB-read call, not the rest of the function."""
    from ui.sky_east._shared import get_progress_lookup
    from ui.session_keys import SK

    st.session_state.pop(SK.SE_PROGRESS_LKUP, None)

    captured = {}
    records = [{"style": "DR5124", "pc_no": "HHPPC048"}]

    class _FakeLookup:
        @classmethod
        def from_records(cls, recs):
            captured["records"] = recs
            return "BUILT"

    class _FakeStore:
        def load_progress_records(self, source):
            return records

    monkeypatch.setattr("ui.stores.get_store", lambda: _FakeStore())
    monkeypatch.setattr(
        "po_extractor.lookups.progress_lookup.ProgressLookup", _FakeLookup
    )

    assert get_progress_lookup("sky_east") == "BUILT"
    assert captured["records"] == records
