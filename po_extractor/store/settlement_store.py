"""Store for the settlement statistics module (结算统计表).

The workbook stays the master — this holds an imported copy so the figures can
be queried, cross-checked against the orders the system already knows about,
and reported on in ways a spreadsheet makes awkward (what is owed and by when,
what is at discount risk, what a contract actually earned).

Import replaces per **sheet**, never the whole table: a book usually carries
one client-year that has moved on and several that haven't, and wiping the lot
to re-add unchanged rows would lose nothing but would make a partial upload
destructive.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from typing import Any

import pandas as pd

from .base_store import BaseSQLiteStore
from ._settlement_schema import _SETTLEMENT_SCHEMA

# Columns written per settlement row, in insert order.
_ROW_COLS = (
    "sheet", "client", "year", "currency", "row_no",
    "invoice_no", "po_number", "style", "contract_no", "factory",
    "repeat_or_new", "contract_qty", "unit_cost", "fob", "contract_amount",
    "ex_factory", "shipped_qty", "over_short_pct", "invoice_amount",
    "received", "received_date",
    "pay_fabric", "pay_fabric_date", "pay_trim", "pay_trim_date",
    "pay_cmt", "pay_cmt_date", "fee_port", "fee_other1", "fee_other2",
    "discount_risk", "contract_status",
)
_SAMPLE_COLS = ("style", "client", "factory", "fabric", "lining", "rib",
                "trim", "total", "row_no")


class SettlementStore(BaseSQLiteStore):
    """Read/write access to the settlement_* tables."""

    _checked_paths: set[str] = set()

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path not in SettlementStore._checked_paths:
            self._ensure_schema()
            SettlementStore._checked_paths.add(db_path)

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SETTLEMENT_SCHEMA)

    # ── import ──────────────────────────────────────────────────────────────

    def import_parsed(self, parsed: dict[str, Any], *, source_file: str = "",
                      file_bytes: bytes | None = None,
                      imported_by: str = "") -> dict[str, Any]:
        """Replace the sheets *parsed* contains.  Returns a per-sheet summary.

        Sheets absent from the upload keep whatever they had — a book with one
        client-year removed must not silently delete that year's history.
        The 样品 table is replaced whole, because it is a single flat list
        rather than one list per sheet.
        """
        now = datetime.now().isoformat(timespec="seconds")
        rows = parsed.get("rows") or []
        samples = parsed.get("samples") or []
        sheets = sorted({str(r.get("sheet") or "") for r in rows})
        digest = (hashlib.sha256(bytes(file_bytes)).hexdigest()
                  if file_bytes else "")

        before = self.rows_by_sheet()
        with self._conn() as conn:
            for name in sheets:
                conn.execute("DELETE FROM settlements WHERE sheet=?", (name,))
            conn.executemany(
                f"INSERT INTO settlements ({','.join(_ROW_COLS)}, "
                "imported_at, imported_by) VALUES "
                f"({','.join('?' * len(_ROW_COLS))}, ?, ?)",
                [tuple(r.get(c) for c in _ROW_COLS) + (now, imported_by)
                 for r in rows],
            )
            if samples:
                conn.execute("DELETE FROM settlement_samples")
                conn.executemany(
                    f"INSERT INTO settlement_samples ({','.join(_SAMPLE_COLS)},"
                    " imported_at, imported_by) VALUES "
                    f"({','.join('?' * len(_SAMPLE_COLS))}, ?, ?)",
                    [tuple(s.get(c) for c in _SAMPLE_COLS) + (now, imported_by)
                     for s in samples],
                )
            conn.execute(
                """INSERT INTO settlement_imports
                      (source_file, source_hash, sheets, n_rows, n_samples,
                       skipped, imported_at, imported_by)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (source_file, digest, ", ".join(sheets), len(rows),
                 len(samples), "; ".join(parsed.get("skipped") or []),
                 now, imported_by))

        after = self.rows_by_sheet()
        return {
            "sheets": [{"sheet": s, "before": before.get(s, 0),
                        "after": after.get(s, 0)} for s in sheets],
            "n_rows": len(rows), "n_samples": len(samples),
            "untouched": sorted(set(before) - set(sheets)),
        }

    def rows_by_sheet(self) -> dict[str, int]:
        with self._conn() as conn:
            return {r["sheet"]: int(r["n"]) for r in conn.execute(
                "SELECT sheet, COUNT(*) AS n FROM settlements GROUP BY sheet")}

    # ── read ────────────────────────────────────────────────────────────────

    def list_rows(self, *, clients: list[str] | None = None,
                  years: list[str] | None = None,
                  factories: list[str] | None = None,
                  search: str = "") -> pd.DataFrame:
        """Settlement lines with the derived money columns already worked out.

        ``outstanding``, ``cost_total`` and ``margin`` are computed here rather
        than stored: they are functions of columns in the same row, and a
        stored copy would be one import away from disagreeing with them.
        """
        sql = ["SELECT * FROM settlements WHERE 1=1"]
        args: list[Any] = []
        for col, vals in (("client", clients), ("year", years),
                          ("factory", factories)):
            if vals:
                sql.append(f"AND {col} IN ({','.join('?' * len(vals))})")
                args.extend(vals)
        if search.strip():
            like = f"%{search.strip()}%"
            sql.append("AND (invoice_no LIKE ? OR po_number LIKE ? "
                       "OR style LIKE ? OR contract_no LIKE ? "
                       "OR factory LIKE ?)")
            args.extend([like] * 5)
        sql.append("ORDER BY year DESC, client, invoice_no, row_no")
        with self._conn() as conn:
            df = pd.DataFrame([dict(r) for r in
                               conn.execute(" ".join(sql), args).fetchall()])
        return _with_derived(df)

    def list_samples(self) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.DataFrame([dict(r) for r in conn.execute(
                "SELECT * FROM settlement_samples ORDER BY client, style")])

    def list_imports(self, limit: int = 20) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.DataFrame([dict(r) for r in conn.execute(
                "SELECT * FROM settlement_imports "
                "ORDER BY datetime(imported_at) DESC, id DESC LIMIT ?",
                (limit,))])

    def distinct(self, column: str) -> list[str]:
        """Sorted distinct values of one column, for the filter widgets."""
        if column not in ("client", "year", "factory", "sheet", "currency"):
            raise ValueError(f"not a filterable column: {column}")
        with self._conn() as conn:
            return [str(r[0]) for r in conn.execute(
                f"SELECT DISTINCT {column} FROM settlements "
                f"WHERE TRIM(COALESCE({column},'')) <> '' ORDER BY {column}")]

    # ── cross-reference with the orders the system already holds ────────────

    def match_orders(self) -> pd.DataFrame:
        """Each settlement line against the Sky East item it settles.

        Matched on the client's PO **and** the style: a PO covers several
        styles and each is invoiced separately, so the PO alone would fan one
        settlement line out across all of them.  ``po_number`` here is the
        client's own PO — the same thing Sky East stores as ``zalando_po`` —
        not a GIII ``po_number``, which is a different number entirely.

        Returns an empty frame when the Sky East tables aren't in this
        database, the same guard the cut-plan store uses.
        """
        sql = """
            SELECT s.id, s.sheet, s.invoice_no, s.po_number, s.style,
                   s.contract_no, s.contract_qty, s.shipped_qty,
                   s.currency, s.client, s.year,
                   i.pc_no          AS se_pc_no,
                   i.total_qty      AS se_qty,
                   i.ex_fty_date    AS se_ex_fty,
                   i.color_name     AS se_color
              FROM settlements s
              LEFT JOIN sky_east_items i
                ON TRIM(i.zalando_po) = TRIM(s.po_number)
               AND TRIM(i.style)      = TRIM(s.style)
             WHERE TRIM(s.po_number) <> ''
             ORDER BY s.year DESC, s.invoice_no
        """
        try:
            with self._conn() as conn:
                return pd.DataFrame([dict(r) for r in
                                     conn.execute(sql).fetchall()])
        except sqlite3.OperationalError:
            return pd.DataFrame()

    def unmatched_pos(self) -> pd.DataFrame:
        """Settlement lines naming a PO the system has never seen.

        Usually a typo or a PO that was never imported — either way it is the
        list worth acting on, because those lines can't be checked against
        anything.
        """
        df = self.match_orders()
        if df.empty or "se_qty" not in df.columns:
            return df
        return df[df["se_qty"].isna()].copy()


def _with_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``outstanding``, ``cost_total`` and ``margin`` to a rows frame."""
    if df.empty:
        for col in ("outstanding", "cost_total", "margin"):
            df[col] = pd.Series(dtype="float64")
        return df

    def n(col: str) -> pd.Series:
        return pd.to_numeric(df.get(col), errors="coerce").fillna(0)

    # Billed falls back to the contract amount: a line that has shipped but
    # not been invoiced is still owed, and would otherwise read as settled.
    billed = pd.to_numeric(df.get("invoice_amount"), errors="coerce")
    billed = billed.fillna(pd.to_numeric(df.get("contract_amount"),
                                         errors="coerce")).fillna(0)
    df["outstanding"] = (billed - n("received")).round(2)
    df["cost_total"] = (n("pay_fabric") + n("pay_trim") + n("pay_cmt")
                        + n("fee_port") + n("fee_other1")
                        + n("fee_other2")).round(2)
    earned = pd.to_numeric(df.get("received"), errors="coerce").fillna(billed)
    # None, not 0, where nothing has been paid out — "break even" and "not
    # costed yet" are different claims.
    df["margin"] = (earned - df["cost_total"]).round(2)
    df.loc[df["cost_total"] == 0, "margin"] = pd.NA
    return df
