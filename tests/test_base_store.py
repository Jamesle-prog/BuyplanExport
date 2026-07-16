"""Regression tests for BaseSQLiteStore shared connection helper.

  • _conn() must not propagate an OperationalError raised by the
    ``PRAGMA journal_mode=WAL`` switch (e.g. "database is locked" on the
    very first switch of a brand-new/non-WAL database file under
    concurrent access) -- it should just skip WAL for this connection and
    leave the path unmarked so a later connection retries the switch.
"""
from __future__ import annotations

import sqlite3

from po_extractor.store.base_store import BaseSQLiteStore


class _Store(BaseSQLiteStore):
    """Minimal concrete store -- just enough to exercise _conn()."""
    def __init__(self, db_path):
        self.db_path = str(db_path)


def test_conn_survives_wal_pragma_operational_error(tmp_path, monkeypatch):
    db_path = str(tmp_path / "locked.db")
    # Make sure a previous test run hasn't already marked this (fresh) path.
    BaseSQLiteStore._wal_initialized.discard(db_path)

    class _FailWalConnection(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql.strip() == "PRAGMA journal_mode=WAL":
                raise sqlite3.OperationalError("database is locked")
            return super().execute(sql, *args, **kwargs)

    real_connect = sqlite3.connect

    def _connect_with_spy(path, *a, **kw):
        if path == db_path:
            kw["factory"] = _FailWalConnection
        return real_connect(path, *a, **kw)

    monkeypatch.setattr(sqlite3, "connect", _connect_with_spy)

    store = _Store(db_path)
    conn = store._conn()  # must not raise sqlite3.OperationalError

    assert conn is not None
    assert tuple(conn.execute("SELECT 1").fetchone()) == (1,), (
        "connection must still be usable after the WAL pragma failed"
    )
    assert db_path not in BaseSQLiteStore._wal_initialized, (
        "path must NOT be marked WAL-initialized when the pragma switch failed"
    )
