"""Login audit log store: recording, filtering, counts, maintenance."""
from __future__ import annotations

import pytest

from po_extractor.store.login_log_store import (
    LoginLogStore, OUTCOME_SUCCESS, OUTCOME_FAILED, OUTCOME_LOCKED,
)


@pytest.fixture
def store(tmp_path):
    return LoginLogStore(str(tmp_path / "log.db"))


def test_record_and_list_newest_first(store):
    store.record("alice", OUTCOME_SUCCESS)
    store.record("bob", OUTCOME_FAILED, detail="wrong password")
    rows = store.list_recent()
    assert [r["username"] for r in rows] == ["bob", "alice"]   # newest first
    assert rows[0]["outcome"] == OUTCOME_FAILED
    assert rows[0]["detail"] == "wrong password"
    assert rows[1]["ts"]                                       # timestamp stamped


def test_outcome_and_username_filters(store):
    store.record("alice", OUTCOME_SUCCESS)
    store.record("alice", OUTCOME_FAILED)
    store.record("ADMIN", OUTCOME_SUCCESS)
    assert {r["username"] for r in store.list_recent(outcome=OUTCOME_SUCCESS)} \
        == {"alice", "ADMIN"}
    # username filter is case-insensitive substring
    assert len(store.list_recent(username_like="ali")) == 2
    assert len(store.list_recent(username_like="admin")) == 1


def test_unknown_outcome_is_stored_as_failed(store):
    store.record("x", "banana")
    assert store.list_recent()[0]["outcome"] == OUTCOME_FAILED


def test_counts(store):
    store.record("a", OUTCOME_SUCCESS)
    store.record("a", OUTCOME_SUCCESS)      # same user, 2 logins
    store.record("b", OUTCOME_SUCCESS)
    store.record("c", OUTCOME_FAILED)
    store.record("c", OUTCOME_LOCKED)
    c = store.counts()
    assert c == {"total": 5, "success": 3, "failed": 1, "locked": 1, "users": 2}


def test_last_login_returns_latest_success_only(store):
    store.record("alice", OUTCOME_FAILED)
    assert store.last_login("alice") is None
    store.record("alice", OUTCOME_SUCCESS)
    first = store.last_login("alice")
    store.record("alice", OUTCOME_SUCCESS)
    second = store.last_login("alice")
    assert first is not None and second is not None
    assert store.last_login("nobody") is None


def test_limit_caps_rows(store):
    for i in range(10):
        store.record(f"u{i}", OUTCOME_SUCCESS)
    assert len(store.list_recent(limit=3)) == 3


def test_ip_is_recorded(store):
    store.record("alice", OUTCOME_SUCCESS, ip="203.0.113.7")
    assert store.list_recent()[0]["ip"] == "203.0.113.7"


def test_clear_empties_the_log(store):
    store.record("a", OUTCOME_SUCCESS)
    store.record("b", OUTCOME_SUCCESS)
    assert store.clear() == 2
    assert store.list_recent() == []


def test_record_never_raises_on_bad_input(store):
    # None username / weird types must not blow up the login it records.
    store.record(None, OUTCOME_SUCCESS)          # type: ignore[arg-type]
    assert store.list_recent()[0]["username"] == ""
