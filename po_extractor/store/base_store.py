"""Shared SQLite connection helper for all store classes."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd



def current_actor() -> str:
    """Best-effort: the signed-in Streamlit user, else ``'system'``.

    Used for audit columns (``changed_by`` / ``updated_by``).  Works outside
    Streamlit (tests, the LAN scan service) where it always says ``system``.
    """
    try:
        import streamlit as st
        from ui.session_keys import SK
        return str(st.session_state.get(SK.USERNAME) or "system").strip() or "system"
    except Exception:
        return "system"


def rows_to_df(rows, columns: list[str] | None = None) -> pd.DataFrame:
    """``sqlite3.Row`` results as a DataFrame.

    With *columns*, an empty result still comes back with those headers (a
    downstream ``df[col]`` on an empty frame would otherwise KeyError);
    without, an empty result is a bare ``pd.DataFrame()``.
    """
    rows = list(rows)
    if not rows:
        return pd.DataFrame(columns=columns) if columns else pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows], columns=columns)


class BaseSQLiteStore:
    """Mixin that provides a consistent ``_conn()`` context-manager for SQLite stores.

    Subclass ``__init__`` must set ``self.db_path`` (str) *before* calling
    ``_conn()``.  The base class does *not* define ``__init__`` so subclasses
    can keep their own signatures.

    Every connection is configured with WAL journal mode and NORMAL
    synchronous level for good concurrency and write performance.
    """

    db_path: str  # set by subclass

    # Paths whose journal_mode has already been set to WAL this process.
    # journal_mode=WAL is a *persisted* DB property, so it only needs to be
    # applied once per file — re-running it on every connection is pure
    # overhead (≈5× the cost of a bare connect).  synchronous=NORMAL is a
    # per-connection setting and is cheap, so it stays on every open.
    _wal_initialized: set[str] = set()

    # (class qualname, db_path) pairs whose schema has been created / migrated
    # this process.  Every store's constructor used to carry its own copy of
    # this guard (or none at all, re-running CREATE TABLE + PRAGMA probes on
    # every instantiation); it lives here now — see ``_init_db``.
    _schema_ready: set[tuple[str, str]] = set()

    # ── construction ────────────────────────────────────────────────────────

    def _init_db(self, db_path: "str | Path", *, mkdir: bool = False) -> None:
        """Set ``db_path`` and run :meth:`_setup_schema` once per (class,
        path) for the life of the process.

        Call from ``__init__``.  ``mkdir`` creates the parent directory first
        (stores that may be the first to touch a fresh ``data/`` folder).
        """
        self.db_path = str(db_path)
        if mkdir:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        key = (type(self).__qualname__, self.db_path)
        if key in BaseSQLiteStore._schema_ready:
            return
        with self._conn() as conn:
            self._setup_schema(conn)
        BaseSQLiteStore._schema_ready.add(key)

    def _setup_schema(self, conn: sqlite3.Connection) -> None:
        """Create tables / run migrations on *conn*.  Override per store;
        runs inside ``with self._conn()`` so it is committed on return."""

    @classmethod
    def _forget_schema(cls, db_path: "str | Path | None" = None) -> None:
        """Drop the once-per-process guard for this class (all paths, or one)
        so the next construction re-runs :meth:`_setup_schema`.  Tests that
        hand-build an older schema at a path use this."""
        gone = {k for k in BaseSQLiteStore._schema_ready
                if k[0] == cls.__qualname__
                and (db_path is None or k[1] == str(db_path))}
        BaseSQLiteStore._schema_ready -= gone

    # ── migrations ──────────────────────────────────────────────────────────

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        """Column names of *table* (empty set when the table does not exist)."""
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    @classmethod
    def _ensure_columns(cls, conn: sqlite3.Connection, table: str,
                        columns: Iterable[tuple[str, str]]) -> None:
        """ADD COLUMN for every ``(name, definition)`` in *columns* that
        *table* lacks — one PRAGMA, tolerant of a concurrent winner."""
        existing = cls._table_columns(conn, table)
        for name, col_def in columns:
            if name not in existing:
                cls._add_column_if_missing(conn, table, name, col_def)

    @staticmethod
    def _add_column_if_missing(conn: sqlite3.Connection, table: str,
                               col_name: str, col_def: str) -> None:
        """ALTER TABLE ... ADD COLUMN, tolerating a concurrent winner.

        First-run migrations are check-then-act (PRAGMA table_info → ALTER):
        two session threads hitting a freshly upgraded DB can both see the
        column missing and both issue the ALTER — the loser used to crash its
        tab with ``duplicate column name``.  Losing that race is fine; any
        other OperationalError still propagates.
        """
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc).lower():
                raise

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if self.db_path not in BaseSQLiteStore._wal_initialized:
            # The pragma returns the *resulting* mode — the switch can fail
            # (e.g. the DB is locked by another connection), so only mark the
            # path done once WAL actually took effect; otherwise retry on the
            # next connection.
            try:
                mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                if str(mode).lower() == "wal":
                    BaseSQLiteStore._wal_initialized.add(self.db_path)
            except sqlite3.OperationalError:
                # e.g. "database is locked" on the very first switch of a
                # brand-new/non-WAL file under concurrent access — don't crash
                # the connection, just leave the path unmarked so a later
                # connection retries the switch.
                pass
        conn.execute("PRAGMA synchronous=NORMAL")
        # Wait (up to 5s) for a competing writer instead of failing immediately
        # with "database is locked" — matters when several PDAs write stocktake
        # counts concurrently through the scan modules.
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
