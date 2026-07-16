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
from ._fabric_version_schema import (
    _VERSION_SCHEMA, _ALL_FABRIC_COLUMNS, _DIFF_FIELDS, _SNAPSHOT_KEEP_VERSIONS,
)


def _current_actor() -> str:
    """Best-effort: return the logged-in Streamlit user, else 'system'.

    Mirrors ColorTranslationStore._current_actor() -- same fallback shape,
    kept as an independent copy per this codebase's existing convention of
    not sharing that helper across store modules.
    """
    try:
        import streamlit as st
        from ui.session_keys import SK
        return str(st.session_state.get(SK.USERNAME) or "system").strip() or "system"
    except Exception:
        return "system"


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
            conn.executescript(_VERSION_SCHEMA)
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
                FabricMasterStore._add_column_if_missing(
                    conn, "fabric_master", col_name, col_type
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
        # try/finally: a mid-import exception used to skip wb.close(), and on
        # Windows the open zip handle kept the uploaded file locked until GC —
        # an immediate retry of the same file failed with a share violation.
        try:
            return self._import_from_open_workbook(wb, xlsx_path, source_file_name)
        finally:
            wb.close()

    def _import_from_open_workbook(self, wb, xlsx_path: str,
                                   source_file_name: str | None) -> dict:
        if "all" not in wb.sheetnames:
            raise ValueError("Sheet 'all' not found in workbook.")

        ws = wb["all"]
        imported_at = datetime.utcnow().isoformat()
        source_file = source_file_name or Path(xlsx_path).name

        field_to_col, unmatched = _build_col_map(ws)
        col_field_pairs = [(col, field) for field, col in field_to_col.items()]

        inserted = updated = skipped = 0
        actor = _current_actor()

        with self._conn() as conn:
            # ── Versioning: capture the OLD state before this import's upsert.
            # Read from the PREVIOUS version's own snapshot, not a live
            # fabric_master read -- "Clear & Reimport" already ran delete_all()
            # in its own committed transaction before we get here, so a live
            # read at this point would see an already-empty table.
            v_prev_row = conn.execute(
                "SELECT MAX(version_id) AS v FROM fabric_versions"
            ).fetchone()
            v_prev = v_prev_row["v"] if v_prev_row and v_prev_row["v"] is not None else None

            if v_prev is not None:
                old_rows = conn.execute(
                    f"SELECT quality_no, {', '.join(_DIFF_FIELDS)} "
                    f"FROM fabric_master_snapshot WHERE version_id=?",
                    (v_prev,),
                ).fetchall()
            else:
                # First tracked import ever -- fall back to a live read
                # (captures legacy pre-versioning data). Known gap: if THIS
                # first import is a Clear & Reimport, delete_all() already
                # destroyed that legacy baseline, so version 1's diff will
                # show everything as "added" with nothing "removed".
                old_rows = conn.execute(
                    f"SELECT quality_no, {', '.join(_DIFF_FIELDS)} FROM fabric_master"
                ).fetchall()
            old_state = {r["quality_no"]: dict(r) for r in old_rows}

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

            # ── Versioning: diff FIRST, and only mint a new version when the
            # data actually changed. A byte-identical re-upload used to bump
            # the version anyway -- writing a duplicate snapshot, an empty
            # diff, and (worst) pruning a genuinely different older snapshot
            # out of the retention window to make room for the no-op copy.
            # The diff compares _DIFF_FIELDS only (imported_at/source_file/
            # display_key excluded), so a re-upload of the same data under a
            # new filename/timestamp still counts as unchanged.
            new_rows = conn.execute(
                f"SELECT {', '.join(_ALL_FABRIC_COLUMNS)} FROM fabric_master"
            ).fetchall()
            new_state = {r["quality_no"]: dict(r) for r in new_rows}
            diff_rows = self._compute_version_diff(old_state, new_state)

            if v_prev is not None and not diff_rows:
                # Nothing changed vs the latest version -- no new version.
                # (The upsert above still refreshed imported_at/source_file on
                # the live table; that's import metadata, not fabric data.)
                return {
                    "inserted": inserted,
                    "updated": updated,
                    "skipped": skipped,
                    "total": inserted + updated,
                    "col_map": {f: c for f, c in field_to_col.items()},
                    "unmatched_headers": unmatched,
                    "version_id": v_prev,
                    "unchanged": True,
                }

            # First-ever import (v_prev None) always creates version 1, even
            # with an empty diff -- a baseline snapshot must exist for future
            # imports to compare against.
            new_version_id = 1 if v_prev is None else v_prev + 1

            conn.execute(
                """INSERT INTO fabric_versions
                      (version_id, created_at, uploaded_by, source_file,
                       row_count, inserted, updated, skipped)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (new_version_id, imported_at, actor, source_file,
                 len(new_state), inserted, updated, skipped),
            )

            if new_state:
                cols = ", ".join(_ALL_FABRIC_COLUMNS)
                ph = ", ".join("?" * len(_ALL_FABRIC_COLUMNS))
                conn.executemany(
                    f"INSERT INTO fabric_master_snapshot (version_id, {cols}) "
                    f"VALUES (?, {ph})",
                    [
                        (new_version_id,) + tuple(rec.get(c) for c in _ALL_FABRIC_COLUMNS)
                        for rec in new_state.values()
                    ],
                )

            if diff_rows:
                conn.executemany(
                    """INSERT INTO fabric_version_diff
                          (version_id, quality_no, change_type, field, old_value, new_value, diffed_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    [(new_version_id, *row, imported_at) for row in diff_rows],
                )

            # Prune snapshot DATA older than the retention window --
            # fabric_versions / fabric_version_diff rows are never pruned
            # (permanent audit trail).
            conn.execute(
                "DELETE FROM fabric_master_snapshot WHERE version_id <= ?",
                (new_version_id - _SNAPSHOT_KEEP_VERSIONS,),
            )

        return {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "total": inserted + updated,
            "col_map": {f: c for f, c in field_to_col.items()},
            "unmatched_headers": unmatched,
            "version_id": new_version_id,
            "unchanged": False,
        }

    @staticmethod
    def _diff_value_norm(field: str, value) -> str:
        """Canonical string form of *value* for version-diff comparison.

        Numeric fabric fields are capped at 2 decimal places before
        comparing: the fabric tables' numbers are only meaningful to 2 dp,
        so precision noise beyond that (Excel float artifacts, a source file
        carrying 66.666667 where 66.67 is already on file, int-vs-float
        representation like 200 vs 200.0) must not register as a "changed"
        field -- and hence must not mint a new version by itself.
        """
        if value is None:
            return ""
        if field in _NUMERIC_FIELDS:
            try:
                return str(round(float(value), 2))
            except (ValueError, TypeError):
                pass   # non-numeric text in a numeric column: string-compare
        return str(value)

    @classmethod
    def _compute_version_diff(cls, old_state: dict, new_state: dict) -> list[tuple]:
        """Return one (quality_no, change_type, field, old_value, new_value)
        tuple per added/removed quality_no, and one per changed field for a
        quality_no present in both -- mirrors ColorTranslationStore._audit_diff's
        field-level diff shape. Empty list == the two states are identical
        across _DIFF_FIELDS (i.e. no version bump warranted). Numeric fields
        compare (and are recorded) at 2 dp -- see _diff_value_norm."""
        rows: list[tuple] = []
        for qno in set(old_state) | set(new_state):
            old_row = old_state.get(qno)
            new_row = new_state.get(qno)
            if old_row is None:
                rows.append((qno, "added", None, None, None))
            elif new_row is None:
                rows.append((qno, "removed", None, None, None))
            else:
                for f in _DIFF_FIELDS:
                    ov_s = cls._diff_value_norm(f, old_row.get(f))
                    nv_s = cls._diff_value_norm(f, new_row.get(f))
                    if ov_s != nv_s:
                        rows.append((qno, "changed", f, ov_s, nv_s))
        return rows

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

    def get_batch_enrichment(self, fabric_nos: list, version_id: int | None = None) -> dict:
        """Return {fabric_no: record} for all requested fabric numbers in one pass.

        *version_id*=None (default) reads the live ``fabric_master`` table --
        unchanged behavior for every existing caller. A specific *version_id*
        reads the archived ``fabric_master_snapshot`` for that version instead
        (only the current + 3 most recent versions have snapshot data
        available; an older, pruned version_id simply returns no matches).
        """
        table = "fabric_master" if version_id is None else "fabric_master_snapshot"
        extra_where = "" if version_id is None else " AND version_id=?"
        _SQL = f"""SELECT quality_no, erp_code, display_key,
                         composition_en, weight_gsm, cuttable_width_cm,
                         shrinkage_rate, short_rate
                  FROM {table} WHERE {{col}} IN ({{ph}}){extra_where}"""
        keys = list({str(f).strip() for f in fabric_nos if f})
        if not keys:
            return {}

        version_args = [] if version_id is None else [version_id]
        result: dict = {}
        ph = ",".join("?" * len(keys))
        with self._conn() as conn:
            rows = conn.execute(
                _SQL.format(col="quality_no", ph=ph), keys + version_args
            ).fetchall()
            matched_by_qno = set()
            for row in rows:
                d = dict(row)
                result[d["quality_no"]] = d
                matched_by_qno.add(d["quality_no"])

            unmatched = [k for k in keys if k not in matched_by_qno]
            if unmatched:
                ph2 = ",".join("?" * len(unmatched))
                for row in conn.execute(
                    _SQL.format(col="erp_code", ph=ph2), unmatched + version_args
                ).fetchall():
                    d = dict(row)
                    result[d["erp_code"]] = d

        return result

    # ── Versioning: read/query API ───────────────────────────────────────────

    def list_versions(self, limit: int = 20) -> list[dict]:
        """Return version metadata, newest first -- for populating a version picker."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT version_id, created_at, uploaded_by, source_file,
                          row_count, inserted, updated, skipped
                   FROM fabric_versions ORDER BY version_id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_diff_summary(self, version_id: int) -> dict:
        """Return {'added': n, 'removed': n, 'changed': n} distinct-quality_no
        counts for one version's diff (a 'changed' quality_no may have several
        field rows, counted once)."""
        summary = {"added": 0, "removed": 0, "changed": 0}
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT change_type, COUNT(DISTINCT quality_no) AS n
                   FROM fabric_version_diff WHERE version_id=?
                   GROUP BY change_type""",
                (version_id,),
            ).fetchall()
        for r in rows:
            summary[r["change_type"]] = r["n"]
        return summary

    def get_version_diff(self, version_id: int) -> list[dict]:
        """Return every diff row for one version, for the detail view."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT quality_no, change_type, field, old_value, new_value, diffed_at
                   FROM fabric_version_diff WHERE version_id=?
                   ORDER BY quality_no, id""",
                (version_id,),
            ).fetchall()
        return [dict(r) for r in rows]

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
                "rows_read":      int,   # rows read from source
                "net_added":      int,   # net new rows in destination
                                          # (= dst_count_after - dst_count_before)
                "already_in_dst": int,   # rows in dst before migration
                "message":        str,   # human-readable summary
            }
        """
        import sqlite3 as _sqlite3

        # ── Read from source ────────────────────────────────────────────────
        src_conn = None
        try:
            src_conn = _sqlite3.connect(src_db_path)
            src_conn.row_factory = _sqlite3.Row
            has_table = src_conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='fabric_master'"
            ).fetchone()
            if not has_table:
                return {"rows_read": 0, "net_added": 0, "already_in_dst": 0,
                        "message": "Source DB has no fabric_master table."}

            src_rows = src_conn.execute("SELECT * FROM fabric_master").fetchall()
            if not src_rows:
                return {"rows_read": 0, "net_added": 0, "already_in_dst": 0,
                        "message": "Source fabric_master is empty — nothing to migrate."}

            # Column names from the source
            src_cols = [desc[0] for desc in src_conn.execute(
                "SELECT * FROM fabric_master LIMIT 0"
            ).description]
        except Exception as exc:
            return {"rows_read": 0, "net_added": 0, "already_in_dst": 0,
                    "message": f"Cannot read source DB: {exc}"}
        finally:
            if src_conn is not None:
                src_conn.close()

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
            # Quote column identifiers so reserved-word or whitespace-bearing
            # column names round-trip safely.  Doubling embedded `"` per the
            # SQL-92 escaping rule keeps the SQL well-formed even with
            # adversarial schemas.
            col_list = ", ".join(f'"{c.replace(chr(34), chr(34)*2)}"' for c in common)
            ph       = ", ".join("?" * len(common))
            rows_to_insert = [
                tuple(row[c] for c in common) for row in src_rows
            ]
            dst_conn.executemany(
                f"INSERT OR REPLACE INTO fabric_master ({col_list}) VALUES ({ph})",
                rows_to_insert,
            )

        net_added = dst_store.count() - already_in_dst
        return {
            "rows_read":      len(src_rows),
            "net_added":      net_added,
            "already_in_dst": already_in_dst,
            "message": (
                f"Read {len(src_rows)} rows from source DB; "
                f"{net_added} added to destination "
                f"({already_in_dst} were already present)."
            ),
        }
