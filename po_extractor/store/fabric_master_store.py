"""SQLite-backed store for the fabric master database (面料统计表).

Imports from the '面料统计表.xlsx' 'all' sheet and exposes lookup by
公司面料编号 (Quality No.).

Schema DDL, header-alias tables, column-map fallback, and low-level row
helpers are kept in _fabric_master_schema.py to separate static definitions
from the store class logic.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import openpyxl

from .base_store import BaseSQLiteStore
from ._fabric_master_schema import (
    _SCHEMA, _NUMERIC_FIELDS,
    _build_col_map, _v, _num, _make_display_key,
)


class FabricMasterStore(BaseSQLiteStore):
    """Read/write access to the fabric_master SQLite table."""

    # Summary columns used by search / list_all / list_page (no expensive fields)
    _SUMMARY_COLS = (
        "quality_no", "erp_code", "supplier", "composition_en",
        "weight_gsm", "cuttable_width_cm", "dyeing_process",
        "shrinkage_rate", "short_rate", "notes_cn", "display_key",
    )

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_schema()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_schema(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            self._migrate_swap_widths(conn)
            self._migrate_add_spot_price_cols(conn)

    @staticmethod
    def _migrate_add_spot_price_cols(conn: sqlite3.Connection) -> None:
        """Add is_in_stock / spot_price_kg / spot_price_m columns if missing.

        BUG-11 fix: the NULL-clearing UPDATE previously fired unconditionally
        whenever spot_price_kg was absent from the schema — which is always true
        on a fresh install, wiping any fabric data already imported in the same
        session.  Now we use user_version=2 as a sentinel so the destructive
        UPDATE only runs once on databases that genuinely pre-date this migration.
        New installations jump straight to version 2 without touching data.
        """
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= 2:
            return  # migration already applied, nothing to do

        existing_cols = {
            row[1] for row in conn.execute("PRAGMA table_info(fabric_master)").fetchall()
        }

        for col_name, col_type in [
            ("is_in_stock",  "TEXT"),
            ("spot_price_kg", "REAL"),
            ("spot_price_m",  "REAL"),
        ]:
            if col_name not in existing_cols:
                conn.execute(
                    f"ALTER TABLE fabric_master ADD COLUMN {col_name} {col_type}"
                )

        # Only NULL out stale data when upgrading a pre-existing DB that lacked
        # the spot_price_kg column.  On a fresh install existing_cols already
        # contains the column (added by the DDL in _SCHEMA), so this branch is
        # skipped and no data is touched.
        if "spot_price_kg" not in existing_cols:
            conn.execute(
                """UPDATE fabric_master
                   SET cost_per_kg    = NULL,
                       cost_per_m     = NULL,
                       quote_date     = NULL,
                       shrinkage_rate = NULL,
                       short_rate     = NULL,
                       notes_cn       = NULL,
                       notes_en       = NULL,
                       quote_history  = NULL"""
            )

        conn.execute("PRAGMA user_version = 2")

    @staticmethod
    def _migrate_swap_widths(conn: sqlite3.Connection) -> None:
        """One-time migration: swap full_width_cm ↔ cuttable_width_cm if reversed."""
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= 1:
            return

        needs_swap = conn.execute(
            """SELECT COUNT(*) FROM fabric_master
               WHERE cuttable_width_cm IS NOT NULL
                 AND full_width_cm IS NOT NULL
                 AND cuttable_width_cm > full_width_cm"""
        ).fetchone()[0]

        if needs_swap:
            # BUG-34 fix: the previous UPDATE had no WHERE clause, so it swapped
            # cuttable ↔ full for EVERY row — corrupting rows that were already
            # correct.  Restrict the swap to rows that actually need it (the
            # same predicate used to detect the issue).
            conn.execute(
                """UPDATE fabric_master
                   SET cuttable_width_cm = full_width_cm,
                       full_width_cm     = cuttable_width_cm
                   WHERE cuttable_width_cm IS NOT NULL
                     AND full_width_cm IS NOT NULL
                     AND cuttable_width_cm > full_width_cm"""
            )
            # Rebuild display_key only for the rows whose width just changed
            rows = conn.execute(
                """SELECT quality_no, composition_en, weight_gsm, cuttable_width_cm
                   FROM fabric_master
                   WHERE cuttable_width_cm IS NOT NULL"""
            ).fetchall()
            for row in rows:
                qno   = row[0]
                comp  = row[1] or ""
                gsm   = str(int(row[2])) if row[2] else ""
                width = str(int(row[3])) if row[3] else ""
                key   = f"{qno}|{comp}|{gsm}|{width}"
                conn.execute(
                    "UPDATE fabric_master SET display_key=? WHERE quality_no=?",
                    (key, qno),
                )

        conn.execute("PRAGMA user_version = 1")

    # ── Import ────────────────────────────────────────────────────────────────

    def import_from_xlsx(self, xlsx_path: str,
                         source_file_name: str | None = None) -> dict:
        """Import all rows from the 'all' sheet of 面料统计表.xlsx.

        Returns a summary dict:
            {"inserted": int, "updated": int, "skipped": int, "total": int,
             "col_map": dict, "unmatched_headers": list}
        """
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        if "all" not in wb.sheetnames:
            wb.close()
            raise ValueError("Sheet 'all' not found in workbook.")

        ws = wb["all"]
        imported_at = datetime.utcnow().isoformat()
        source_file = source_file_name or Path(xlsx_path).name

        field_to_col, unmatched = _build_col_map(ws)
        col_field_pairs = [(col, field) for field, col in field_to_col.items()]

        inserted = updated = skipped = 0

        with self._conn() as conn:
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                record: dict = {}
                for col_idx, field in col_field_pairs:
                    raw = row[col_idx - 1] if col_idx - 1 < len(row) else None
                    if field in _NUMERIC_FIELDS:
                        record[field] = _num(raw)
                    elif field == "quote_date":
                        if raw is None:
                            record[field] = None
                        elif hasattr(raw, "isoformat"):
                            record[field] = raw.date().isoformat()
                        else:
                            record[field] = _v(raw) or None
                    else:
                        record[field] = _v(raw) or None

                quality_no = record.get("quality_no")
                if not quality_no:
                    skipped += 1
                    continue

                record["display_key"] = _make_display_key(
                    quality_no,
                    record.get("composition_en") or "",
                    record.get("weight_gsm"),
                    record.get("cuttable_width_cm"),
                )
                record["imported_at"] = imported_at
                record["source_file"] = source_file

                existing = conn.execute(
                    "SELECT quality_no FROM fabric_master WHERE quality_no=?",
                    (quality_no,)
                ).fetchone()

                fields = list(record.keys())
                values = [record[f] for f in fields]

                if existing:
                    set_clause = ", ".join(f"{f}=?" for f in fields if f != "quality_no")
                    vals = [record[f] for f in fields if f != "quality_no"] + [quality_no]
                    conn.execute(
                        f"UPDATE fabric_master SET {set_clause} WHERE quality_no=?",
                        vals,
                    )
                    updated += 1
                else:
                    placeholders = ", ".join("?" * len(fields))
                    conn.execute(
                        f"INSERT INTO fabric_master ({', '.join(fields)}) VALUES ({placeholders})",
                        values,
                    )
                    inserted += 1

        wb.close()
        return {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "total": inserted + updated,
            "col_map": {f: c for f, c in field_to_col.items()},
            "unmatched_headers": unmatched,
        }

    # ── Lookups ───────────────────────────────────────────────────────────────

    def get_by_quality_no(self, quality_no: str) -> dict | None:
        """Return full record dict or None. Matches quality_no or erp_code."""
        key = quality_no.strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM fabric_master WHERE quality_no=? OR erp_code=?",
                (key, key),
            ).fetchone()
        return dict(row) if row else None

    def get_key_info(self, fabric_no: str) -> dict | None:
        """Return 6 key fields for display, or None. Matches quality_no or erp_code."""
        key = fabric_no.strip()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT composition_en, weight_gsm, cuttable_width_cm,
                          shrinkage_rate, short_rate, notes_cn
                   FROM fabric_master WHERE quality_no=? OR erp_code=?""",
                (key, key),
            ).fetchone()
        return dict(row) if row else None

    def get_display_key(self, fabric_no: str) -> str:
        """Return 'quality_no|composition_en|weight_gsm|cuttable_width_cm' or empty str."""
        key = fabric_no.strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT display_key FROM fabric_master WHERE quality_no=? OR erp_code=?",
                (key, key),
            ).fetchone()
        return row["display_key"] if row else ""

    def get_batch_enrichment(self, fabric_nos: list) -> dict:
        """Return {fabric_no: record} for all requested fabric numbers in one pass."""
        _SQL = """SELECT quality_no, erp_code, display_key,
                         composition_en, weight_gsm, cuttable_width_cm,
                         shrinkage_rate, short_rate
                  FROM fabric_master WHERE {col} IN ({ph})"""
        keys = list({str(f).strip() for f in fabric_nos if f})
        if not keys:
            return {}

        result: dict = {}
        ph = ",".join("?" * len(keys))
        with self._conn() as conn:
            rows = conn.execute(_SQL.format(col="quality_no", ph=ph), keys).fetchall()
            matched_by_qno = set()
            for row in rows:
                d = dict(row)
                result[d["quality_no"]] = d
                matched_by_qno.add(d["quality_no"])

            unmatched = [k for k in keys if k not in matched_by_qno]
            if unmatched:
                ph2 = ",".join("?" * len(unmatched))
                for row in conn.execute(_SQL.format(col="erp_code", ph=ph2), unmatched).fetchall():
                    d = dict(row)
                    result[d["erp_code"]] = d

        return result

    def search(self, query: str, limit: int = 200) -> list[dict]:
        """Search by quality_no, composition_en, supplier, or structure_en."""
        q = f"%{query.strip()}%"
        cols = ", ".join(self._SUMMARY_COLS)
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT {cols}
                   FROM fabric_master
                   WHERE quality_no LIKE ? OR composition_en LIKE ?
                      OR supplier LIKE ? OR structure_en LIKE ?
                   ORDER BY quality_no
                   LIMIT ?""",
                (q, q, q, q, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self, limit: int = 5000) -> list[dict]:
        """Return all records (summary columns only)."""
        cols = ", ".join(self._SUMMARY_COLS) + ", imported_at, source_file"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {cols} FROM fabric_master ORDER BY quality_no LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_page(self, offset: int = 0, limit: int = 200) -> list[dict]:
        """Return one page of records (summary columns only), ordered by quality_no."""
        cols = ", ".join(self._SUMMARY_COLS) + ", imported_at, source_file"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {cols} FROM fabric_master ORDER BY quality_no LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all_compositions(self) -> list[dict]:
        """Return {quality_no, composition_en} for every record — used for validation."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT quality_no, composition_en FROM fabric_master ORDER BY quality_no"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_all(self) -> int:
        """Delete every row from fabric_master. Returns the number of rows removed."""
        with self._conn() as conn:
            n = conn.execute("SELECT COUNT(*) FROM fabric_master").fetchone()[0]
            conn.execute("DELETE FROM fabric_master")
        return n

    def delete_by_quality_nos(self, quality_nos: list[str]) -> int:
        """Delete rows whose quality_no is in *quality_nos*. Returns rows deleted."""
        if not quality_nos:
            return 0
        keys = [str(q).strip() for q in quality_nos if q]
        ph   = ",".join("?" * len(keys))
        with self._conn() as conn:
            cur = conn.execute(
                f"DELETE FROM fabric_master WHERE quality_no IN ({ph})", keys
            )
        return cur.rowcount

    def list_all_quality_nos(self) -> list[str]:
        """Return all quality_no values for cross-system HHN orphan checks."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT quality_no FROM fabric_master WHERE quality_no IS NOT NULL"
            ).fetchall()
        return [r[0] for r in rows]

    def list_all_for_validation(self) -> list[dict]:
        """Return all records with the fields needed for field-range validation."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT quality_no, weight_gsm, cuttable_width_cm, full_width_cm,
                          shrinkage_rate, short_rate
                   FROM fabric_master ORDER BY quality_no"""
            ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM fabric_master").fetchone()[0]

    def last_import_info(self) -> dict | None:
        """Return imported_at and source_file of the most recent import."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT imported_at, source_file FROM fabric_master "
                "ORDER BY imported_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # ── Cross-DB migration ─────────────────────────────────────────────────────

    @classmethod
    def migrate_from_db(cls, src_db_path: str, dst_db_path: str) -> dict:
        """Copy the fabric_master table from one SQLite database to another.

        Designed for the one-time migration from the legacy shared ``po_history.db``
        into the dedicated ``fabric_master.db``.  Reads rows into Python memory
        from the source then bulk-inserts into the destination — avoids ATTACH
        transaction-locking issues that occur in WAL mode.

        Existing rows in *dst_db_path* with matching ``quality_no`` are replaced.

        Returns::
            {
                "migrated": int,   # rows copied from source
                "already_in_dst": int,  # rows in dst before migration
                "message": str,    # human-readable summary
            }
        """
        import sqlite3 as _sqlite3

        # ── Read from source ────────────────────────────────────────────────
        try:
            src_conn = _sqlite3.connect(src_db_path)
            src_conn.row_factory = _sqlite3.Row
            has_table = src_conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='fabric_master'"
            ).fetchone()
            if not has_table:
                src_conn.close()
                return {"migrated": 0, "already_in_dst": 0,
                        "message": "Source DB has no fabric_master table."}

            src_rows = src_conn.execute("SELECT * FROM fabric_master").fetchall()
            if not src_rows:
                src_conn.close()
                return {"migrated": 0, "already_in_dst": 0,
                        "message": "Source fabric_master is empty — nothing to migrate."}

            # Column names from the source
            src_cols = [desc[0] for desc in src_conn.execute(
                "SELECT * FROM fabric_master LIMIT 0"
            ).description]
            src_conn.close()
        except Exception as exc:
            return {"migrated": 0, "already_in_dst": 0,
                    "message": f"Cannot read source DB: {exc}"}

        # ── Ensure destination schema, then write ───────────────────────────
        dst_store = cls(dst_db_path)
        already_in_dst = dst_store.count()

        # Only insert columns present in the destination schema.
        with dst_store._conn() as dst_conn:
            dst_cols = {
                row[1]
                for row in dst_conn.execute(
                    "PRAGMA table_info(fabric_master)"
                ).fetchall()
            }
            common = [c for c in src_cols if c in dst_cols]
            col_list = ", ".join(common)
            ph       = ", ".join("?" * len(common))
            rows_to_insert = [
                tuple(row[c] for c in common) for row in src_rows
            ]
            dst_conn.executemany(
                f"INSERT OR REPLACE INTO fabric_master ({col_list}) VALUES ({ph})",
                rows_to_insert,
            )

        migrated = dst_store.count() - already_in_dst
        return {
            "migrated": len(src_rows),
            "already_in_dst": already_in_dst,
            "message": (
                f"Copied {len(src_rows)} rows from source DB "
                f"({already_in_dst} were already present in destination)."
            ),
        }
