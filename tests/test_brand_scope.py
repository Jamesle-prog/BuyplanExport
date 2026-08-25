"""Brand scope for 船样要求 — who looks after which brand.

Company access is the gate and is decided first; brands narrow within it.
The empty list therefore means the OPPOSITE of what it means for companies:
no brand restriction. Getting that backwards would lock every existing
account out of a screen they use today, since none has brands assigned.
"""
from __future__ import annotations

import json

import pytest

from auth import users as U


@pytest.fixture
def users_file(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    f.write_text(json.dumps({
        "boss":  {"password": "x", "role": "admin", "companies": [],
                  "modules": [], "factories": [], "brands": []},
        "angel": {"password": "x", "role": "user", "companies": ["Sky East"],
                  "modules": [], "factories": [], "brands": ["Even&Odd"]},
        "chen":  {"password": "x", "role": "user", "companies": ["Sky East"],
                  "modules": [], "factories": [], "brands": []},
    }), encoding="utf-8")
    monkeypatch.setattr(U, "_USERS_FILE", str(f))
    return f


# ── The scope itself ────────────────────────────────────────────────────────

def test_a_user_gets_the_brands_they_look_after(users_file):
    assert U.get_user_brands("angel") == ["Even&Odd"]


def test_no_brands_means_no_restriction_not_no_access(users_file):
    """The opposite of the company rule, deliberately — see the module
    docstring. If this ever returns "nothing", every existing account loses a
    screen it uses today."""
    assert U.get_user_brands("chen") == []


def test_an_admin_is_never_brand_restricted(users_file):
    assert U.get_user_brands("boss") == []


def test_an_unknown_user_gets_nothing(users_file):
    assert U.get_user_brands("nobody") == []


def test_brands_can_be_reassigned(users_file):
    assert U.set_user_brands("chen", ["Anna Field"]) is True
    assert U.get_user_brands("chen") == ["Anna Field"]
    assert U.set_user_brands("nobody", ["X"]) is False


def test_a_password_change_does_not_wipe_the_brand_scope(users_file, monkeypatch):
    """create_user is also the password-change path; a scope silently emptied
    there is a permission change nobody asked for."""
    monkeypatch.setattr(U, "verify_password", lambda u, p: True)
    assert U.change_password("angel", "old", "new") is True
    assert U.get_user_brands("angel") == ["Even&Odd"]


def test_creating_a_user_without_brands_keeps_the_existing_ones(users_file):
    U.create_user("angel", "pw2", role="user", companies=["Sky East"])
    assert U.get_user_brands("angel") == ["Even&Odd"]


# ── The editor honours it ───────────────────────────────────────────────────

def _rows():
    return [
        {"company": "Sky East", "brand": "Even&Odd", "req_text": "A", "updated_at": ""},
        {"company": "Sky East", "brand": "Anna Field", "req_text": "B", "updated_at": ""},
    ]


class _FakeStore:
    def __init__(self, rows): self._rows = rows; self.deleted = []
    def list_all(self): return self._rows
    def get(self, c, b): return ""
    def delete(self, c, b): self.deleted.append((c, b)); return 1


def _run(monkeypatch, brands_allowed):
    pytest.importorskip("streamlit")
    import ui.boat_sample_view as bs
    store = _FakeStore(_rows())
    shown = []
    monkeypatch.setattr(bs, "get_boat_sample_store", lambda: store)
    monkeypatch.setattr(bs, "list_all_brands",
                        lambda c: ["Even&Odd", "Anna Field"])
    monkeypatch.setattr(bs.st, "dataframe", lambda df, **k: shown.append(df))
    monkeypatch.setattr(bs.st, "selectbox", lambda label, *a, **k: None)
    monkeypatch.setattr(bs.st, "button", lambda *a, **k: False)
    bs.render_boat_sample_editor(["Sky East"], key_prefix="bsr_t",
                                 brands_allowed=brands_allowed)
    return shown


def test_a_scoped_user_sees_only_their_brand(monkeypatch):
    shown = _run(monkeypatch, ["Even&Odd"])
    assert len(shown) == 1
    assert list(shown[0].iloc[:, 1]) == ["Even&Odd"]


def test_an_unscoped_user_still_sees_every_brand(monkeypatch):
    """The regression that would hurt most: this is today's behaviour for
    every account, and the new field must not change it."""
    shown = _run(monkeypatch, [])
    assert sorted(shown[0].iloc[:, 1]) == ["Anna Field", "Even&Odd"]
    shown = _run(monkeypatch, None)
    assert sorted(shown[0].iloc[:, 1]) == ["Anna Field", "Even&Odd"]


def test_the_write_is_re_checked_against_the_brand_scope():
    """Filtering the dropdown isn't enough — the widget key outlives it."""
    import inspect
    import ui.boat_sample_view as bs
    src = inspect.getsource(bs.render_boat_sample_editor)
    assert "brand_scope and brand_v not in brand_scope" in src
    assert 'brand_scope and target["brand"] not in brand_scope' in src
