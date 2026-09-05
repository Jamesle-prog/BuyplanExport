"""Persistent progress-records (大货进度表) mixin for POStore.

Requires self._conn() from BaseSQLiteStore.
"""
from __future__ import annotations

from datetime import datetime

from ..utils.normalize import normalize_key as _norm_key

# Columns written/read on progress_records, in a fixed order shared by the
# batch-save and record-load paths so the two stay in sync. pc_no_norm is
# derived at save time (not part of the parsed-record shape) so it's handled
# separately from this list.
_PROGRESS_COLUMNS = [
    "contract_no", "pc_no", "style", "style_norm", "brand", "test_note",
    "color_summary", "color_en", "color_norm", "color_cn", "color_code",
    "label_color", "ex_fty_date", "launch_date", "qty", "remarks",
    "zalando_po", "fabric_detail",
]

# Maps a progress_lookup.py parsed-record key -> the progress_records DB column.
_RECORD_TO_DB = {
    "contract_no":   "contract_no",
    "pc_no":         "pc_no",
    "style_display": "style",
    "style":         "style_norm",
    "brand":         "brand",
    "test_note":     "test_note",
    "color_summary": "color_summary",
    "color":         "color_en",
    "color_norm":    "color_norm",
    "cn_color":      "color_cn",
    "color_code":    "color_code",
    "label_color":   "label_color",
    "ex_fty":        "ex_fty_date",
    "launch_date":   "launch_date",
    "qty":           "qty",
    "remarks":       "remarks",
    "zalando_po":    "zalando_po",
    "fabric":        "fabric_detail",
}

# Reverse map — a progress_records DB column -> the record key
# ProgressLookup._index_records() / from_records() expects.
_DB_TO_RECORD = {
    "contract_no":   "contract_no",
    "pc_no":         "pc_no",
    "style":         "style_display",
    "style_norm":    "style",
    "brand":         "brand",
    "test_note":     "test_note",
    "color_summary": "color_summary",
    "color_en":      "color",
    "color_norm":    "color_norm",
    "color_cn":      "cn_color",
    "color_code":    "color_code",
    "label_color":   "label_color",
    "ex_fty_date":   "ex_fty",
    "launch_date":   "launch_date",
    "qty":           "qty",
    "remarks":       "remarks",
    "zalando_po":    "zalando_po",
    "fabric_detail": "fabric",
}


class _ProgressMixin:
    """Progress-records (大货进度表) operations for POStore.
    Requires self._conn() from BaseSQLiteStore.
    """

    def save_progress_records_batch(self, source: str, records: list[dict]) -> int:
        """Upsert progress records (as produced by
        ``progress_lookup.parse_progress_rows()``) for *source*.

        Row identity is ``(source, pc_no_norm, style_norm, color_norm)`` —
        the same normalised key ``ProgressLookup`` already uses to resolve a
        contract line, so re-uploading an updated file (even with slightly
        different PC-number casing/whitespace) overwrites the same rows
        instead of creating duplicates.

        Returns the number of rows upserted.
        """
        if not records:
            return 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        count = 0
        with self._conn() as conn:
            for rec in records:
                db_row = {
                    db_col: rec.get(rec_key, "")
                    for rec_key, db_col in _RECORD_TO_DB.items()
                }
                # style_norm is the primary identity component — skip a row
                # that can't be identified (no usable style).
                if not db_row.get("style_norm"):
                    continue
                qty_val = db_row.get("qty")
                db_row["qty"] = "" if qty_val is None else str(qty_val)
                pc_no_norm = _norm_key(db_row.get("pc_no") or "")

                cols = _PROGRESS_COLUMNS
                placeholders = ",".join("?" * len(cols))
                update_clause = ", ".join(
                    f"{c} = excluded.{c}" for c in cols
                    if c not in ("style_norm", "color_norm")
                )
                conn.execute(
                    f"""INSERT INTO progress_records
                        (source, pc_no_norm, {", ".join(cols)}, updated_at)
                        VALUES (?, ?, {placeholders}, ?)
                        ON CONFLICT(source, pc_no_norm, style_norm, color_norm) DO UPDATE SET
                            {update_clause}, updated_at = excluded.updated_at
                    """,
                    [source, pc_no_norm] + [db_row.get(c, "") for c in cols] + [now],
                )
                count += 1
        return count

    def load_progress_records(self, source: str | None = None) -> list[dict]:
        """Return progress records for *source* in the shape
        ``ProgressLookup._index_records()`` / ``from_records()`` expects.

        ``source=None`` returns every company's records (rarely useful —
        callers normally scope to one company).
        """
        clauses, params = [], []
        if source:
            clauses.append("source = ?")
            params.append(source)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM progress_records {where}", params,
            ).fetchall()

        records: list[dict] = []
        for r in rows:
            rec = {rec_key: (r[db_col] or "") for db_col, rec_key in _DB_TO_RECORD.items()}
            rec["image_id"] = ""   # not persisted — see table comment in schema
            records.append(rec)
        return records

    def list_progress_keys(self, source: str) -> set[tuple[str, str, str]]:
        """Return the set of ``(pc_no_norm, style_norm, color_norm)`` keys
        already stored for *source* — used to classify an incoming upload's
        rows as new vs. already-existing.
        """
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT pc_no_norm, style_norm, color_norm FROM progress_records WHERE source=?",
                (source,),
            ).fetchall()
        return {
            (r["pc_no_norm"] or "", r["style_norm"] or "", r["color_norm"] or "")
            for r in rows
        }

    def get_progress_records_by_keys(
        self, source: str, keys: list[tuple[str, str, str]],
    ) -> dict[tuple[str, str, str], dict]:
        """Return ``{(pc_no_norm, style_norm, color_norm): db_row_dict}`` for
        the given keys — used to diff an incoming upload's rows against
        what's already stored.
        """
        if not keys:
            return {}
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM progress_records WHERE source=?", (source,),
            ).fetchall()
        wanted = set(keys)
        result: dict[tuple[str, str, str], dict] = {}
        for r in rows:
            key = (r["pc_no_norm"] or "", r["style_norm"] or "", r["color_norm"] or "")
            if key in wanted:
                result[key] = dict(r)
        return result

    def count_progress_records(self, source: str) -> int:
        """Return how many progress records are stored for *source*."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM progress_records WHERE source=?", (source,),
            ).fetchone()
        return row["n"] if row else 0

    def delete_progress_records(self, source: str) -> int:
        """Delete every progress record for *source*. Returns rows deleted."""
        with self._conn() as conn:
            return conn.execute(
                "DELETE FROM progress_records WHERE source=?", (source,),
            ).rowcount
