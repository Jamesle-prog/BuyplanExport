"""Regression test for the 船样要求 delete control (originally Fix 8).

The delete dropdown used to encode the selection as a single
"{company} / {brand}" string and recover the two parts with
`split(" / ", 1)`. A company name that itself contains " / " breaks that
round-trip (e.g. "Acme / Sub" + "BrandA" -> "Acme / Sub / BrandA" ->
split(" / ", 1) -> ("Acme", "Sub / BrandA"), which is wrong). The fix selects
by index into the original (company, brand) rows instead.

The editor moved to ui/boat_sample_view.py when regular users gained the
ability to maintain their own company's entries; this exercises it through the
admin mount point, which is where the bug was found.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.boat_sample_view as bs


class _FakeStore:
    def __init__(self, rows):
        self._rows = rows
        self.deleted: list[tuple[str, str]] = []

    def list_all(self):
        return self._rows

    def get(self, company, brand):
        return ""

    def delete(self, company, brand):
        self.deleted.append((company, brand))
        return 1


def _run_editor(monkeypatch, rows, companies, *, picked_index):
    store = _FakeStore(rows)
    monkeypatch.setattr(bs, "get_boat_sample_store", lambda: store)
    monkeypatch.setattr(bs, "list_all_brands", lambda company: [])

    def _fake_selectbox(label, *args, **kwargs):
        key = kwargs.get("key")
        if key == "bsr_admin_company":
            return companies[0]
        if key == "bsr_admin_del":
            return picked_index
        return None

    monkeypatch.setattr(bs.st, "selectbox", _fake_selectbox)
    monkeypatch.setattr(bs.st, "button",
                        lambda label, *a, **k: k.get("key") == "bsr_admin_del_btn")
    monkeypatch.setattr(bs.st, "rerun", lambda: None)
    bs.render_boat_sample_editor(companies, key_prefix="bsr_admin")
    return store


def test_delete_selects_by_index_when_company_contains_separator(monkeypatch):
    rows = [
        {"company": "Acme / Sub", "brand": "BrandA", "req_text": "text",  "updated_at": "2026-01-01"},
        {"company": "Other Co",   "brand": "BrandB", "req_text": "text2", "updated_at": "2026-01-01"},
    ]
    store = _run_editor(monkeypatch, rows, ["Acme / Sub", "Other Co"],
                        picked_index=0)
    # Must delete the FIRST row's exact (company, brand) — not the
    # mis-split ("Acme", "Sub / BrandA") the old string-split code produced.
    assert store.deleted == [("Acme / Sub", "BrandA")]


def test_a_row_outside_the_allowed_companies_is_never_deleted(monkeypatch):
    """Rows are scoped on read, so this shouldn't be reachable — but the delete
    re-checks anyway. A widget key outlives the options that filled it, so a
    company can still sit in session state after access to it is withdrawn."""
    rows = [
        {"company": "Mine",     "brand": "BrandA", "req_text": "", "updated_at": ""},
        {"company": "Not Mine", "brand": "BrandB", "req_text": "", "updated_at": ""},
    ]
    store = _run_editor(monkeypatch, rows, ["Mine"], picked_index=0)
    # "Not Mine" was filtered out of rows entirely, so index 0 is "Mine".
    assert store.deleted == [("Mine", "BrandA")]


def test_only_the_allowed_companies_rows_are_listed(monkeypatch):
    rows = [
        {"company": "Mine",     "brand": "BrandA", "req_text": "x", "updated_at": ""},
        {"company": "Not Mine", "brand": "BrandB", "req_text": "y", "updated_at": ""},
    ]
    shown: list = []
    monkeypatch.setattr(bs.st, "dataframe",
                        lambda df, **k: shown.append(df))
    _run_editor(monkeypatch, rows, ["Mine"], picked_index=None)
    assert len(shown) == 1
    assert list(shown[0].iloc[:, 0]) == ["Mine"]      # the other company's row is absent


def test_the_box_prefills_with_what_is_on_file(monkeypatch):
    """Editing must be a correction, not a retype from memory — the reason a
    user returns here after the brand's first upload.

    This broke silently once already: Streamlit ignores `value=` once a keyed
    widget exists, so the text is assigned into session state instead.
    """
    rows = [{"company": "Mine", "brand": "BrandA",
             "req_text": "3 pcs before bulk", "updated_at": ""}]
    store = _FakeStore(rows)
    store.get = lambda company, brand: (           # type: ignore[assignment]
        "3 pcs before bulk" if (company, brand) == ("Mine", "BrandA") else "")

    monkeypatch.setattr(bs, "get_boat_sample_store", lambda: store)
    monkeypatch.setattr(bs, "list_all_brands", lambda company: ["BrandA"])
    monkeypatch.setattr(bs.st, "selectbox",
                        lambda label, *a, **k: "BrandA"
                        if k.get("key") == "bsr_x_brand" else None)
    monkeypatch.setattr(bs.st, "button", lambda *a, **k: False)

    bs.render_boat_sample_editor(["Mine"], key_prefix="bsr_x")
    assert bs.st.session_state["bsr_x_text"] == "3 pcs before bulk"


def test_switching_target_reloads_the_box(monkeypatch):
    """A stale text box would let one brand's requirement be saved onto
    another."""
    store = _FakeStore([])
    texts = {("Mine", "A"): "text A", ("Mine", "B"): "text B"}
    store.get = lambda c, b: texts.get((c, b), "")   # type: ignore[assignment]
    monkeypatch.setattr(bs, "get_boat_sample_store", lambda: store)
    monkeypatch.setattr(bs, "list_all_brands", lambda company: ["A", "B"])
    monkeypatch.setattr(bs.st, "button", lambda *a, **k: False)

    for brand, expected in [("A", "text A"), ("B", "text B"), ("A", "text A")]:
        monkeypatch.setattr(bs.st, "selectbox",
                            lambda label, *a, _b=brand, **k: _b
                            if k.get("key") == "bsr_y_brand" else None)
        bs.render_boat_sample_editor(["Mine"], key_prefix="bsr_y")
        assert bs.st.session_state["bsr_y_text"] == expected
