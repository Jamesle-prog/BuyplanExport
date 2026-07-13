"""Shared SQLite connection helper for all store classes."""
from __future__ import annotations

import sqlite3
from pathlib import Path


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
            mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() == "wal":
                BaseSQLiteStore._wal_initialized.add(self.db_path)
        conn.execute("PRAGMA synchronous=NORMAL")
        # Wait (up to 5s) for a competing writer instead of failing immediately
        # with "database is locked" — matters when several PDAs write stocktake
        # counts concurrently through the scan modules.
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
