"""UPC lookup + stocktake (盘点) operations for the PDA scan module.

Requires ``self._conn()`` from BaseSQLiteStore.

Scope note: ``find_by_upc`` is company-scoped, but the stocktake count is keyed
by UPC alone (``upc_stocktake.upc`` is the PK) and is therefore GLOBAL — not
per-company. In a single-tenant deployment that's what you want (one physical
count per barcode); a multi-company deployment would share counts. Both scan
surfaces (the Streamlit UPC Check tab and the ``web_scan`` service) share this
one table, which is how their counts stay in sync.
"""
from __future__ import annotations

from datetime import datetime


class _UpcMixin:
    # ── lookup ────────────────────────────────────────────────────────────────

    def find_by_upc(self, upc: str, companies: list[str] | None = None) -> list[dict]:
        """Return every stored size row whose UPC matches, joined to its PO's
        client / destination-warehouse metadata. A UPC can appear on more than
        one PO, so all matches are returned (newest PO first).

        Each row: po_number, style, color, size, units, upc, xfty_date,
        company, destination_code, ship_to, buyer, customer, division_name.
        *companies* scopes to the caller's assigned clients (None = all)."""
        upc = str(upc or "").strip()
        if not upc:
            return []
        sql = """
            SELECT s.po_number, s.style, s.color, s.size, s.units, s.upc,
                   s.xfty_date, m.company, m.destination_code, m.ship_to,
                   m.buyer, m.customer, m.division_name
            FROM po_size_rows s
            LEFT JOIN po_metadata m ON m.po_number = s.po_number
            WHERE s.upc = ?
        """
        params: list = [upc]
        if companies:
            ph = ",".join("?" * len(companies))
            sql += f" AND m.company IN ({ph})"
            params += list(companies)
        sql += " ORDER BY m.extracted_at DESC"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    # ── stocktake (盘点) ──────────────────────────────────────────────────────

    def adjust_stocktake(self, upc: str, delta: int) -> int:
        """Add *delta* (+1 / -1) to a UPC's stocktake count; return the new
        total. Counts may go negative (an over-scan on the decrease pass is a
        real signal, not something to silently clamp)."""
        upc = str(upc or "").strip()
        if not upc:
            return 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO upc_stocktake (upc, qty, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(upc) DO UPDATE SET
                     qty = qty + ?, updated_at = ?""",
                (upc, delta, now, delta, now),
            )
            row = conn.execute(
                "SELECT qty FROM upc_stocktake WHERE upc = ?", (upc,)).fetchone()
        return row["qty"] if row else 0

    def load_stocktake(self, include_zero: bool = False) -> list[dict]:
        """Return stocktake counts joined to PO/style/color/size context.

        One row per (upc): {upc, qty, updated_at, po_number, style, color,
        size}. Non-zero only unless *include_zero*."""
        having = "" if include_zero else "WHERE t.qty != 0"
        with self._conn() as conn:
            # Take po/style/color/size from ONE size row per UPC (the lowest
            # rowid) so the context is internally consistent — a per-column
            # MIN() could mix a style from one PO with a colour from another
            # when a UPC appears on several POs.
            rows = conn.execute(f"""
                SELECT t.upc, t.qty, t.updated_at,
                       s.po_number, s.style, s.color, s.size
                FROM upc_stocktake t
                LEFT JOIN (
                    SELECT upc, po_number, style, color, size
                    FROM po_size_rows
                    WHERE rowid IN (SELECT MIN(rowid) FROM po_size_rows GROUP BY upc)
                ) s ON s.upc = t.upc
                {having}
                ORDER BY t.updated_at DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def clear_stocktake(self) -> int:
        """Wipe all stocktake counts; return how many rows were removed."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM upc_stocktake")
            return cur.rowcount or 0
