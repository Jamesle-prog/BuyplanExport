"""Who changed what — the app-wide audit trail.

Two properties matter more than the rest and are tested hardest:

* the acting user must never leak between concurrent sessions (Streamlit runs
  each browser session in its own thread, on a server several people share);
* auditing must never break the write it describes — a failing log is an
  inconvenience, a failed contract save is lost work.
"""
from __future__ import annotations

import threading

import pytest

from po_extractor.store import audit_context as ctx
from po_extractor.store.change_log_store import (
    ACTION_CREATE, ACTION_DELETE, ACTION_UPDATE, ENTITY_BOAT_SAMPLE,
    ENTITY_USER, ChangeLogStore,
)


@pytest.fixture(autouse=True)
def _clean_context():
    ctx.clear_current_user()
    yield
    ctx.clear_current_user()


@pytest.fixture
def store(tmp_path):
    ChangeLogStore._checked_paths.clear()
    return ChangeLogStore(str(tmp_path / "cl.db"))


# ── The acting user ─────────────────────────────────────────────────────────

def test_the_change_records_the_signed_in_user(store):
    ctx.set_current_user("angel")
    store.record(ENTITY_BOAT_SAMPLE, "Sky East / Even&Odd",
                 field="req_text", old="", new="3 pcs")
    row = store.list_recent().iloc[0]
    assert row["username"] == "angel"
    assert row["old_value"] == "" and row["new_value"] == "3 pcs"


def test_the_user_never_leaks_between_threads():
    """The one that matters on a shared server: Streamlit runs each browser
    session in its own thread, so one person's identity must never end up on
    another's rows. A module-level global would fail this; thread-local passes.

    Written without a Barrier deliberately -- a synchronisation primitive that
    can deadlock has no place in a suite that must always terminate. Setting
    the user in a child thread and checking BOTH sides afterwards proves
    thread-locality just as well, and cannot hang.
    """
    ctx.set_current_user("james")          # this thread
    child_saw: dict[str, str] = {}

    def work() -> None:
        assert ctx.current_user() == ""    # a fresh thread starts empty
        ctx.set_current_user("angel")
        child_saw["value"] = ctx.current_user()

    th = threading.Thread(target=work)
    th.start()
    th.join(timeout=10)
    assert not th.is_alive(), "child thread did not finish"
    assert child_saw["value"] == "angel"   # the child kept its own user
    assert ctx.current_user() == "james"   # and never touched this one


def test_an_unknown_user_records_blank_rather_than_failing(store):
    """A background job or CLI script has no signed-in user. The change is
    still worth recording."""
    store.record(ENTITY_USER, "bob", field="role", old="user", new="admin")
    assert store.list_recent().iloc[0]["username"] == ""


def test_an_explicit_username_overrides_the_ambient_one(store):
    ctx.set_current_user("angel")
    store.record(ENTITY_USER, "bob", field="role", old="", new="admin",
                 username="system")
    assert store.list_recent().iloc[0]["username"] == "system"


# ── Never break the write it describes ──────────────────────────────────────

def test_a_broken_log_does_not_raise(tmp_path, monkeypatch):
    store = ChangeLogStore(str(tmp_path / "cl2.db"))

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(store, "_conn", boom)
    store.record(ENTITY_USER, "bob", field="role", old="", new="admin")
    store.record_many([{"entity": ENTITY_USER, "record_key": "x"}])


def test_an_unprintable_value_does_not_raise(store):
    class Nasty:
        def __str__(self):
            raise ValueError("nope")
    ctx.set_current_user("angel")
    store.record(ENTITY_USER, "bob", field="thing", old=Nasty(), new="x")
    assert store.list_recent().iloc[0]["old_value"] == "<unprintable>"


def test_long_values_are_clipped_not_stored_whole(store):
    store.record(ENTITY_USER, "bob", field="blob", old="", new="x" * 5000)
    stored = store.list_recent().iloc[0]["new_value"]
    assert len(stored) <= 500 and stored.endswith("…")


# ── Reading ─────────────────────────────────────────────────────────────────

def test_filters_narrow_by_user_entity_and_record(store):
    ctx.set_current_user("angel")
    store.record(ENTITY_BOAT_SAMPLE, "Sky East / Even&Odd", field="req_text")
    ctx.set_current_user("james")
    store.record(ENTITY_USER, "bob", field="role")
    assert len(store.list_recent()) == 2
    assert len(store.list_recent(username="angel")) == 1
    assert len(store.list_recent(entity=ENTITY_USER)) == 1
    assert len(store.list_recent(record_key="even")) == 1     # case-insensitive


def test_record_many_shares_one_timestamp(store):
    """One save that touches several fields reads as one edit, not several."""
    ctx.set_current_user("angel")
    store.record_many([
        {"entity": ENTITY_USER, "record_key": "bob", "field": "role"},
        {"entity": ENTITY_USER, "record_key": "bob", "field": "companies"},
    ])
    df = store.list_recent()
    assert len(df) == 2 and df["ts"].nunique() == 1


def test_an_unknown_action_falls_back_to_update(store):
    store.record(ENTITY_USER, "bob", action="frobnicate")
    assert store.list_recent().iloc[0]["action"] == ACTION_UPDATE


def test_counts_and_facets(store):
    ctx.set_current_user("angel")
    store.record(ENTITY_BOAT_SAMPLE, "a", ACTION_CREATE)
    store.record(ENTITY_USER, "b", ACTION_DELETE)
    c = store.counts()
    assert c["total"] == 2 and c["users"] == 1 and c["today"] == 2
    assert store.entities() == [ENTITY_BOAT_SAMPLE, ENTITY_USER]
    assert store.users() == ["angel"]


def test_purge_removes_only_old_entries(store):
    store.record(ENTITY_USER, "recent")
    assert store.purge_older_than(365) == 0      # nothing is a year old yet
    assert store.purge_older_than(0) == 0        # 0 is a no-op, not "everything"
    assert len(store.list_recent()) == 1


# ── The stores actually write to it ─────────────────────────────────────────

def test_a_boat_sample_edit_is_attributed_end_to_end(tmp_path, monkeypatch):
    """The real path: angel edits a 船样要求, and the log says so."""
    import po_extractor.store as store_pkg
    from po_extractor.store.boat_sample_store import BoatSampleStore

    db = str(tmp_path / "e2e.db")
    ChangeLogStore._checked_paths.clear()
    log = ChangeLogStore(db)
    monkeypatch.setattr(store_pkg, "get_change_log_store", lambda: log)

    BoatSampleStore._checked_paths = getattr(
        BoatSampleStore, "_checked_paths", set())
    bs = BoatSampleStore(db)
    ctx.set_current_user("angel")

    bs.upsert("Sky East", "Even&Odd", "M码齐色2套")      # create
    bs.upsert("Sky East", "Even&Odd", "S码1套")          # update
    bs.delete("Sky East", "Even&Odd")                    # delete

    df = log.list_recent()
    assert list(df["action"]) == [ACTION_DELETE, ACTION_UPDATE, ACTION_CREATE]
    assert set(df["username"]) == {"angel"}
    assert set(df["record_key"]) == {"Sky East / Even&Odd"}
    upd = df[df["action"] == ACTION_UPDATE].iloc[0]
    assert upd["old_value"] == "M码齐色2套" and upd["new_value"] == "S码1套"


def test_rewriting_the_same_value_records_nothing(tmp_path, monkeypatch):
    """Saving an unchanged value is not a change -- logging it would bury the
    real edits."""
    import po_extractor.store as store_pkg
    from po_extractor.store.boat_sample_store import BoatSampleStore

    db = str(tmp_path / "same.db")
    ChangeLogStore._checked_paths.clear()
    log = ChangeLogStore(db)
    monkeypatch.setattr(store_pkg, "get_change_log_store", lambda: log)

    bs = BoatSampleStore(db)
    ctx.set_current_user("angel")
    bs.upsert("Sky East", "Even&Odd", "3 pcs")
    bs.upsert("Sky East", "Even&Odd", "3 pcs")     # identical
    assert len(log.list_recent()) == 1


def test_an_account_role_change_is_recorded(tmp_path, monkeypatch):
    """Who granted admin -- the first question any audit asks."""
    import json
    import po_extractor.store as store_pkg
    from auth import users as U

    db = str(tmp_path / "acct.db")
    ChangeLogStore._checked_paths.clear()
    log = ChangeLogStore(db)
    monkeypatch.setattr(store_pkg, "get_change_log_store", lambda: log)

    users_file = tmp_path / "users.json"
    users_file.write_text(json.dumps({
        "bob": {"password": "x", "role": "user", "companies": [],
                "modules": [], "factories": [], "brands": []}}),
        encoding="utf-8")
    monkeypatch.setattr(U, "_USERS_FILE", str(users_file))

    ctx.set_current_user("james")
    assert U.set_user_role("bob", "admin") is True

    row = log.list_recent().iloc[0]
    assert row["username"] == "james"          # who did it
    assert row["record_key"] == "bob"          # to whom
    assert row["field"] == "role"
    assert row["old_value"] == "user" and row["new_value"] == "admin"


def test_the_suite_can_never_write_to_the_live_change_log():
    """Pins the conftest firewall.

    The audit hooks record from inside ordinary store methods, so any test
    that exercises a canonical store also exercises them. Twice now that has
    filed real rows into data/po_history.db — 53, then 7 more. Nothing in the
    suite may resolve the live change log; conftest redirects the canonical
    path to a scratch DB, and this fails if that goes away.
    """
    import po_extractor.store as store_pkg
    from po_extractor.config import DB_PATH
    from po_extractor.store.change_log_store import ChangeLogStore

    assert store_pkg.get_change_log_store().db_path != DB_PATH, (
        "the change-log firewall in tests/conftest.py is not in effect — "
        "running the suite would write audit rows into the live database"
    )
    # ...and constructing one on the live path directly is redirected too.
    assert ChangeLogStore(DB_PATH).db_path != DB_PATH
