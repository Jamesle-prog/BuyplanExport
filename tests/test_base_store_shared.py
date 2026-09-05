"""BaseSQLiteStore construction / migration / DataFrame helpers shared by
every store since v2.125.3 (Phase 4 of the refactor)."""
import sqlite3

import pandas as pd

from po_extractor.store.base_store import (
    BaseSQLiteStore, current_actor, rows_to_df,
)


class _Counter(BaseSQLiteStore):
    setups = 0

    def __init__(self, db_path):
        self._init_db(db_path)

    def _setup_schema(self, conn):
        type(self).setups += 1
        conn.executescript("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY, a TEXT);")


class _Other(_Counter):
    setups = 0


def test_init_db_runs_setup_once_per_class_and_path(tmp_path):
    db = str(tmp_path / "x.db")
    _Counter.setups = _Other.setups = 0
    _Counter(db); _Counter(db); _Counter(db)
    assert _Counter.setups == 1
    _Other(db)                                   # a different class, same file
    assert _Other.setups == 1 and _Counter.setups == 1
    _Counter(str(tmp_path / "y.db"))             # a different path
    assert _Counter.setups == 2


def test_forget_schema_reruns_setup(tmp_path):
    db = str(tmp_path / "x.db")
    _Counter.setups = 0
    _Counter(db)
    _Counter._forget_schema(db)
    _Counter(db)
    assert _Counter.setups == 2
    _Counter._forget_schema()                    # all paths for this class
    _Counter(db)
    assert _Counter.setups == 3


def test_init_db_mkdir_creates_parent(tmp_path):
    db = tmp_path / "deep" / "er" / "x.db"

    class _S(BaseSQLiteStore):
        def __init__(self, p):
            self._init_db(p, mkdir=True)

    s = _S(db)
    assert db.parent.is_dir() and s.db_path == str(db)


def test_ensure_columns_adds_only_missing(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "m.db"))
    conn.execute("CREATE TABLE t (id INTEGER, a TEXT)")
    BaseSQLiteStore._ensure_columns(conn, "t", [("a", "TEXT"), ("b", "INTEGER DEFAULT 0"), ("c", "TEXT")])
    assert BaseSQLiteStore._table_columns(conn, "t") == {"id", "a", "b", "c"}
    BaseSQLiteStore._ensure_columns(conn, "t", [("b", "INTEGER")])   # idempotent
    assert BaseSQLiteStore._table_columns(conn, "missing") == set()


def test_rows_to_df_shapes():
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'x'), (2, 'y')")
    df = rows_to_df(conn.execute("SELECT * FROM t").fetchall())
    assert list(df.columns) == ["a", "b"] and df["a"].tolist() == [1, 2]

    empty = rows_to_df([])
    assert empty.empty and list(empty.columns) == []
    empty_cols = rows_to_df([], ["a", "b"])
    assert empty_cols.empty and list(empty_cols.columns) == ["a", "b"]
    # a cursor (not a list) works too, and `columns` re-orders / subsets
    df2 = rows_to_df(conn.execute("SELECT * FROM t"), ["b", "a"])
    assert list(df2.columns) == ["b", "a"]
    assert isinstance(df2, pd.DataFrame)


def test_current_actor_outside_streamlit_is_system():
    assert current_actor() == "system"
