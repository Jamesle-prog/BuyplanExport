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

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
