"""Store for the actual fabric condition module (面料情况).

The source workbook is the master — this holds an imported copy so the shop
floor's fabric log can be searched and browsed without opening Excel. Import
replaces the whole table: unlike the settlement workbook (several
client-years in one file), this is a single running log from one sheet, so
there is no partition to preserve across an upload.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import pandas as pd

from .base_store import BaseSQLiteStore
from ._fabric_condition_schema import _FABRIC_CONDITION_SCHEMA
from ..parsers.fabric_condition import FIELD_ORDER

_RECORD_COLS = ("row_no",) + FIELD_ORDER


class FabricConditionStore(BaseSQLiteStore):
    """Read/write access to the fabric_condition* tables."""

    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path not in FabricConditionStore._checked_paths:
            self._ensure_schema()
            FabricConditionStore._checked_paths.add(db_path)

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_FABRIC_CONDITION_SCHEMA)

    # ── import ──────────────────────────────────────────────────────────────

    def import_parsed(self, parsed: dict[str, Any], *, source_file: str = "",
                      file_bytes: bytes | None = None,
                      imported_by: str = "") -> dict[str, Any]:
        """Replace the whole table with *parsed*'s records."""
        now = datetime.now().isoformat(timespec="seconds")
        records = parsed.get("records") or []
        digest = (hashlib.sha256(bytes(file_bytes)).hexdigest()
                  if file_bytes else "")

        with self._conn() as conn:
            conn.execute("DELETE FROM fabric_condition")
            conn.executemany(
                f"INSERT INTO fabric_condition ({','.join(_RECORD_COLS)}, "
                "imported_at, imported_by) VALUES "
                f"({','.join('?' * len(_RECORD_COLS))}, ?, ?)",
                [tuple(r.get(c) for c in _RECORD_COLS) + (now, imported_by)
                 for r in records],
            )
            conn.execute(
                """INSERT INTO fabric_condition_imports
                      (source_file, source_hash, n_records, imported_at,
                       imported_by)
                   VALUES (?,?,?,?,?)""",
                (source_file, digest, len(records), now, imported_by))
        return {"n_records": len(records)}

    def count(self) -> int:
        with self._conn() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM fabric_condition").fetchone()[0])

    # ── read ────────────────────────────────────────────────────────────────

    def list_records(self, *, styles: list[str] | None = None,
                     colors: list[str] | None = None,
                     search: str = "") -> pd.DataFrame:
        sql = ["SELECT * FROM fabric_condition WHERE 1=1"]
        args: list[Any] = []
        for col, vals in (("style", styles), ("color", colors)):
            if vals:
                sql.append(f"AND {col} IN ({','.join('?' * len(vals))})")
                args.extend(vals)
        if search.strip():
            like = f"%{search.strip()}%"
            sql.append("AND (style LIKE ? OR color LIKE ? OR fabric_no LIKE ?)")
            args.extend([like] * 3)
        sql.append("ORDER BY row_no")
        with self._conn() as conn:
            return pd.DataFrame([dict(r) for r in
                                 conn.execute(" ".join(sql), args).fetchall()])

    def distinct(self, column: str) -> list[str]:
        if column not in ("style", "color", "fabric_no", "body_part"):
            raise ValueError(f"not a filterable column: {column}")
        with self._conn() as conn:
            return [str(r[0]) for r in conn.execute(
                f"SELECT DISTINCT {column} FROM fabric_condition "
                f"WHERE TRIM(COALESCE({column},'')) <> '' ORDER BY {column}")]

    def list_imports(self, limit: int = 20) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.DataFrame([dict(r) for r in conn.execute(
                "SELECT * FROM fabric_condition_imports "
                "ORDER BY datetime(imported_at) DESC, id DESC LIMIT ?",
                (limit,))])
