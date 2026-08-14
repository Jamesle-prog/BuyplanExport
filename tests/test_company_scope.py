"""Company scoping: an account assigned to no company must see nothing.

`get_user_companies` returns `[]` for two opposite situations — an admin
(unrestricted) and a regular user assigned to nothing (no access). Call sites
that collapsed that with `or None` handed an unassigned account the admin's
view of every company's purchase orders. These tests pin both halves of the
fix: the helper that tells the two apart, and the stores failing closed on an
empty list so a mistake upstream can't reopen it.
"""
from __future__ import annotations

import pytest

from auth import users as U
from po_extractor.store.po_store import POStore


@pytest.fixture
def store(tmp_path):
    s = POStore(str(tmp_path / "scope.db"))
    with s._conn() as conn:
        for po, company in [("PO-A", "Company A"), ("PO-B", "Company B")]:
            conn.execute("INSERT INTO po_metadata (po_number, company, extracted_at)"
                         " VALUES (?,?,?)", (po, company, "2026-01-01"))
            conn.execute("INSERT INTO po_size_rows (po_number, style, color, size,"
                         " units, upc) VALUES (?,?,?,?,?,?)",
                         (po, "ST1", "Black", "M", 100, "0123456789012"))
            conn.execute("INSERT INTO po_exceptions (po_number, company, status,"
                         " created_at) VALUES (?,?,?,?)",
                         (po, company, "pending", "2026-01-01"))
    return s


# ── the helper ──────────────────────────────────────────────────────────────

def test_an_admin_is_unrestricted(monkeypatch):
    monkeypatch.setattr(U, "is_admin", lambda u: True)
    monkeypatch.setattr(U, "get_user_companies", lambda u: [])
    assert U.company_scope("boss") is None


def test_an_unassigned_user_is_not_unrestricted(monkeypatch):
    """The whole point: same [] from get_user_companies, opposite meaning."""
    monkeypatch.setattr(U, "is_admin", lambda u: False)
    monkeypatch.setattr(U, "get_user_companies", lambda u: [])
    assert U.company_scope("newbie") == []


def test_an_assigned_user_gets_their_own(monkeypatch):
    monkeypatch.setattr(U, "is_admin", lambda u: False)
    monkeypatch.setattr(U, "get_user_companies", lambda u: ["Company A"])
    assert U.company_scope("angel") == ["Company A"]


# ── the stores fail closed ──────────────────────────────────────────────────

def test_find_by_upc_shows_nothing_for_an_empty_scope(store):
    assert store.find_by_upc("0123456789012", companies=[]) == []


def test_find_by_upc_still_shows_everything_for_none(store):
    rows = store.find_by_upc("0123456789012", companies=None)
    assert sorted({r["company"] for r in rows}) == ["Company A", "Company B"]


def test_find_by_upc_scopes_to_the_listed_company(store):
    rows = store.find_by_upc("0123456789012", companies=["Company A"])
    assert {r["company"] for r in rows} == {"Company A"}


def test_list_pos_shows_nothing_for_an_empty_scope(store):
    assert store.list_pos(companies=[]).empty


def test_list_pos_keeps_its_columns_when_scoped_out(store):
    """An empty frame with no columns breaks callers that filter on them."""
    df = store.list_pos(companies=[])
    assert "po_number" in df.columns and "company" in df.columns


def test_list_exceptions_shows_nothing_for_an_empty_scope(store):
    assert store.list_exceptions(companies=[]).empty


def test_list_exceptions_keeps_its_columns_when_scoped_out(store):
    df = store.list_exceptions(companies=[])
    assert "id" in df.columns and "status" in df.columns


def test_none_and_empty_are_not_the_same_answer(store):
    """The regression in one line: these two used to return the same rows."""
    assert len(store.list_pos(companies=None)) == 2
    assert len(store.list_pos(companies=[])) == 0


# ── acting on an exception must be scoped too ───────────────────────────────

def test_exception_ids_are_scoped(store):
    everything = store.exception_ids(None)
    mine = store.exception_ids(["Company A"])
    assert len(everything) == 2 and len(mine) == 1
    assert mine < everything
    assert store.exception_ids([]) == set()
