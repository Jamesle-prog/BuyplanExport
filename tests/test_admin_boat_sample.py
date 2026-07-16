"""Regression test for ui/admin_boat_sample.py (Fix 8).

The delete-entry dropdown used to encode the selection as a single
"{company} / {brand}" string and recover the two parts with
`split(" / ", 1)`. A company name that itself contains " / " breaks that
round-trip (e.g. "Acme / Sub" + "BrandA" -> "Acme / Sub / BrandA" ->
split(" / ", 1) -> ("Acme", "Sub / BrandA"), which is wrong). The fix selects
by index into the original (company, brand) rows instead.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.admin_boat_sample as ab


class _FakeStore:
    def __init__(self, rows):
        self._rows = rows
        self.deleted: list[tuple[str, str]] = []

    def list_all(self):
        return self._rows

    def delete(self, company, brand):
        self.deleted.append((company, brand))
        return 1


def test_delete_selects_by_index_when_company_contains_separator(monkeypatch):
    rows = [
        {"company": "Acme / Sub", "brand": "BrandA", "req_text": "text",  "updated_at": "2026-01-01"},
        {"company": "Other Co",   "brand": "BrandB", "req_text": "text2", "updated_at": "2026-01-01"},
    ]
    store = _FakeStore(rows)

    monkeypatch.setattr(ab, "get_boat_sample_store", lambda: store)
    monkeypatch.setattr(ab, "list_company_names", lambda active_only=True: ["Acme / Sub", "Other Co"])
    monkeypatch.setattr(ab, "list_all_brands", lambda company: [])

    def _fake_selectbox(label, *args, **kwargs):
        key = kwargs.get("key")
        if key == "bsr_company_sel":
            return "Acme / Sub"
        if key == "bsr_brand_sel":
            return None
        if key == "bsr_del_sel":
            return 0   # simulate picking the FIRST entry: "Acme / Sub / BrandA"
        return None

    monkeypatch.setattr(ab.st, "selectbox", _fake_selectbox)
    monkeypatch.setattr(ab.st, "button", lambda label, *a, **k: k.get("key") == "bsr_del_btn")
    monkeypatch.setattr(ab.st, "rerun", lambda: None)

    ab.show_boat_sample_admin()

    # Must delete the FIRST row's exact (company, brand) — not the
    # mis-split ("Acme", "Sub / BrandA") the old string-split code produced.
    assert store.deleted == [("Acme / Sub", "BrandA")]
