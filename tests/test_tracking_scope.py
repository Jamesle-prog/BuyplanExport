"""Access-control for the 🏭 Tracking module: TrackScope + factory user model.

The security-relevant promise is that a scoped user can never write a row
outside their access, no matter what an uploaded file contains. These tests
lock the enforcement primitive (TrackScope) and the user-model plumbing that
feeds it.
"""
from __future__ import annotations

import json

import pytest

from ui.production_tracking_view import TrackScope


# ── TrackScope.permits ──────────────────────────────────────────────────────

def test_admin_permits_everything():
    s = TrackScope(admin=True, factory_mode=False, allowed_keys=frozenset())
    assert s.permits("ANY-PO", "ANY-STYLE")
    assert s.permits("", "")


def test_client_scope_only_permits_its_keys():
    s = TrackScope(admin=False, factory_mode=False,
                   allowed_keys=frozenset({("PO-SE-1", "STY-A")}))
    assert s.permits("PO-SE-1", "STY-A")
    assert not s.permits("PO-GIII-9", "STY-Z")   # out of scope
    assert not s.permits("PO-SE-1", "STY-B")     # right PO, wrong style


def test_permits_strips_whitespace_on_both_sides():
    s = TrackScope(admin=False, factory_mode=False,
                   allowed_keys=frozenset({("PO-1", "A")}))
    assert s.permits("  PO-1 ", " A ")


# ── TrackScope.sanitize_fields ──────────────────────────────────────────────

def test_factory_user_cannot_write_planned_dates():
    s = TrackScope(admin=False, factory_mode=True, allowed_keys=frozenset())
    out = s.sanitize_fields({
        "cutting_planned": "2026-08-01",   # dropped — planning is not theirs
        "cutting_actual":  "2026-08-05",   # kept — progress
        "cutting_status":  "Done",         # kept
        "cutting_notes":   "on time",      # kept
    })
    assert out == {"cutting_actual": "2026-08-05",
                   "cutting_status": "Done", "cutting_notes": "on time"}


def test_client_user_keeps_planned_dates():
    s = TrackScope(admin=False, factory_mode=False, allowed_keys=frozenset())
    fields = {"cutting_planned": "2026-08-01", "cutting_actual": "2026-08-05"}
    assert s.sanitize_fields(fields) == fields


def test_capability_flags():
    factory = TrackScope(admin=False, factory_mode=True, allowed_keys=frozenset())
    client  = TrackScope(admin=False, factory_mode=False, allowed_keys=frozenset())
    assert not factory.can_edit_planned and not factory.can_add_remove
    assert client.can_edit_planned and client.can_add_remove


# ── User model: factories field ─────────────────────────────────────────────

@pytest.fixture
def users_file(tmp_path, monkeypatch):
    """Point auth.users at a throwaway users.json."""
    import auth.users as u
    f = tmp_path / "users.json"
    monkeypatch.setattr(u, "_USERS_FILE", str(f))
    return u, f


def test_create_user_persists_factories(users_file):
    u, f = users_file
    u.create_user("angel", "pw", role="user", factories=["FAC-1", "FAC-2"])
    assert u.get_user("angel")["factories"] == ["FAC-1", "FAC-2"]
    # And it's actually on disk, not just in memory.
    assert json.loads(f.read_text())["angel"]["factories"] == ["FAC-1", "FAC-2"]


def test_admin_factories_is_empty_meaning_unrestricted(users_file):
    u, _ = users_file
    u.create_user("boss", "pw", role="admin", factories=["FAC-1"])
    # Admins are never factory-restricted, regardless of a stored list.
    assert u.get_user_factories("boss") == []


def test_regular_user_factories_returned(users_file):
    u, _ = users_file
    u.create_user("angel", "pw", role="user", factories=["FAC-1"])
    assert u.get_user_factories("angel") == ["FAC-1"]


def test_set_user_factories(users_file):
    u, _ = users_file
    u.create_user("angel", "pw", role="user")
    assert u.get_user_factories("angel") == []
    assert u.set_user_factories("angel", ["FAC-9"]) is True
    assert u.get_user_factories("angel") == ["FAC-9"]


def test_password_change_preserves_factories(users_file):
    u, _ = users_file
    u.create_user("angel", "pw", role="user", factories=["FAC-1"])
    assert u.change_password("angel", "pw", "pw2") is True
    assert u.get_user_factories("angel") == ["FAC-1"]


def test_factories_default_empty_for_legacy_user(users_file):
    """A user record written before this feature (no 'factories' key) reads
    back as unrestricted, never KeyErrors."""
    u, f = users_file
    f.write_text(json.dumps({
        "angel": {"password": "x", "role": "user", "companies": [], "modules": []}
    }))
    assert u.get_user("angel")["factories"] == []
    assert u.get_user_factories("angel") == []


# ── Store: distinct factories feed the admin picker ─────────────────────────

def test_list_distinct_factories(tmp_path):
    from po_extractor.store.production_tracking_store import ProductionTrackingStore
    import sqlite3

    db = str(tmp_path / "po.db")
    store = ProductionTrackingStore(db)
    with sqlite3.connect(db) as conn:
        for po, fac in [("P1", "FAC-B"), ("P2", "FAC-A"), ("P3", "FAC-A"),
                        ("P4", ""), ("P5", "  ")]:
            conn.execute(
                "INSERT INTO production_tracking (po_number, style, factory) "
                "VALUES (?, '', ?)", (po, fac))
    # Sorted, de-duplicated, blanks/whitespace excluded.
    assert store.list_distinct_factories() == ["FAC-A", "FAC-B"]
