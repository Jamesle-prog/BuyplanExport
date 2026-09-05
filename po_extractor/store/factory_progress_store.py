"""SQLite store for factory progress reports (工厂进度回报).

Dated report log of units cut / sewn / packed per (po_number, style) —
see ``_factory_progress_schema.py`` for the design rationale. Reports come
in via the Excel round-trip (request form sent to the factory, returned
filled-in and imported) or manual entry in the 🏭 Tracking tab; a future
factory-login phase can reuse ``add_report`` unchanged.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .base_store import BaseSQLiteStore
from ._factory_progress_schema import _FACTORY_PROGRESS_SCHEMA, REPORT_STAGES


class FactoryProgressStore(BaseSQLiteStore):
    """Read/write access to the ``factory_progress_reports`` table."""

    def __init__(self, db_path: str):
        self._init_db(db_path)

    def _setup_schema(self, conn) -> None:
        conn.executescript(_FACTORY_PROGRESS_SCHEMA)

    # ── Writes ──────────────────────────────────────────────────────────────

    def add_report(self, po_number: str, style: str, stage: str,
                   report_date: str, units: int, *,
                   factory: str = "", source: str = "manual",
                   notes: str = "", created_by: str = "") -> int:
        """Insert one report row. Returns the new row id.

        *units* must be a positive integer (a report of zero units is not a
        report; corrections are made by deleting the wrong row, keeping the
        log append-only in spirit). *stage* must be a known REPORT_STAGE.
        """
        po_number = (po_number or "").strip()
        style = (style or "").strip()
        if not po_number:
            raise ValueError("po_number is required.")
        if stage not in REPORT_STAGES:
            raise ValueError(f"Unknown stage {stage!r} — expected one of {REPORT_STAGES}.")
        units = int(units)
        if units <= 0:
            raise ValueError("units must be a positive integer.")
        if not (report_date or "").strip():
            raise ValueError("report_date is required.")

        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO factory_progress_reports
                      (po_number, style, factory, stage, report_date, units,
                       source, notes, created_at, created_by)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (po_number, style, (factory or "").strip(), stage,
                 report_date.strip(), units, source, notes or "",
                 datetime.utcnow().isoformat(timespec="seconds"),
                 created_by or ""),
            )
        return int(cur.lastrowid)

    def delete_reports(self, ids: list[int]) -> int:
        """Delete report rows by id (correction path). Returns deleted count."""
        if not ids:
            return 0
        ph = ",".join("?" * len(ids))
        with self._conn() as conn:
            cur = conn.execute(
                f"DELETE FROM factory_progress_reports WHERE id IN ({ph})", ids
            )
        return cur.rowcount

    # ── Reads ───────────────────────────────────────────────────────────────

    def list_reports(self, po_number: str | None = None,
                     style: str | None = None,
                     factory: str | None = None,
                     limit: int = 500) -> list[dict]:
        """Report rows, newest first, optionally filtered."""
        where, params = [], []
        if po_number:
            where.append("po_number=?"); params.append(po_number.strip())
        if style is not None:
            where.append("style=?"); params.append(style.strip())
        if factory:
            where.append("factory=?"); params.append(factory.strip())
        sql = "SELECT * FROM factory_progress_reports"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY report_date DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def totals_for_pairs(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], dict[str, int]]:
        """``{(po_number, style): {"cutting": n, "sewing": n, "packing": n}}``
        for a batch of pairs in one query — every stage key always present
        (0 when never reported). Pairs with no reports at all are omitted.
        """
        keys = list({
            (str(po or "").strip(), str(sty or "").strip()) for po, sty in pairs
        })
        keys = [k for k in keys if k[0]]
        if not keys:
            return {}
        clauses = " OR ".join(["(po_number=? AND style=?)"] * len(keys))
        params = [v for pair in keys for v in pair]
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT po_number, style, stage, SUM(units) AS total
                    FROM factory_progress_reports
                    WHERE {clauses}
                    GROUP BY po_number, style, stage""",
                params,
            ).fetchall()
        out: dict[tuple[str, str], dict[str, int]] = {}
        for r in rows:
            key = (r["po_number"], r["style"])
            if key not in out:
                out[key] = {s: 0 for s in REPORT_STAGES}
            if r["stage"] in out[key]:
                out[key][r["stage"]] = int(r["total"] or 0)
        return out

    def last_report_dates(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], str]:
        """``{(po_number, style): latest report_date}`` for a batch of pairs."""
        keys = list({
            (str(po or "").strip(), str(sty or "").strip()) for po, sty in pairs
        })
        keys = [k for k in keys if k[0]]
        if not keys:
            return {}
        clauses = " OR ".join(["(po_number=? AND style=?)"] * len(keys))
        params = [v for pair in keys for v in pair]
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT po_number, style, MAX(report_date) AS last_date
                    FROM factory_progress_reports
                    WHERE {clauses}
                    GROUP BY po_number, style""",
                params,
            ).fetchall()
        return {(r["po_number"], r["style"]): r["last_date"] or "" for r in rows}

    # ── Order-quantity lookup (for % complete + over-report warnings) ───────

    def order_qty_for_pairs(
        self, pairs: list[tuple[str, str]]
    ) -> dict[tuple[str, str], int]:
        """Ordered units per (po_number, style), from whichever client
        pipeline the PO came through:

          - GIII:      SUM(units) over ``po_size_rows``
          - Sky East:  SUM(xs..xxl) over ``sky_east_items`` (zalando_po)

        Both tables live in the same canonical DB file as this store
        (single-DB deployment — same assumption ``list_untracked_pos`` makes).
        Each source is best-effort: a missing table (partial/legacy DB)
        contributes nothing rather than raising.
        """
        keys = list({
            (str(po or "").strip(), str(sty or "").strip()) for po, sty in pairs
        })
        keys = [k for k in keys if k[0]]
        if not keys:
            return {}
        clauses_ps = " OR ".join(["(po_number=? AND COALESCE(style,'')=?)"] * len(keys))
        clauses_se = " OR ".join(["(zalando_po=? AND COALESCE(style,'')=?)"] * len(keys))
        params = [v for pair in keys for v in pair]

        out: dict[tuple[str, str], int] = {}
        with self._conn() as conn:
            try:
                for r in conn.execute(
                    f"""SELECT po_number, COALESCE(style,'') AS style,
                               SUM(units) AS total
                        FROM po_size_rows WHERE {clauses_ps}
                        GROUP BY po_number, COALESCE(style,'')""",
                    params,
                ).fetchall():
                    out[(r["po_number"], r["style"])] = int(r["total"] or 0)
            except Exception:
                pass
            try:
                for r in conn.execute(
                    f"""SELECT zalando_po AS po_number, COALESCE(style,'') AS style,
                               SUM(COALESCE(xs,0)+COALESCE(s,0)+COALESCE(m,0)
                                   +COALESCE(l,0)+COALESCE(xl,0)+COALESCE(xxl,0)) AS total
                        FROM sky_east_items WHERE {clauses_se}
                        GROUP BY zalando_po, COALESCE(style,'')""",
                    params,
                ).fetchall():
                    key = (r["po_number"], r["style"])
                    out[key] = out.get(key, 0) + int(r["total"] or 0)
            except Exception:
                pass
        return out
