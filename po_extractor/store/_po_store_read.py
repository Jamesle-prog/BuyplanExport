"""Read-side mixin for POStore (list_pos, load_size_rows, load_metadata, etc.)."""
from __future__ import annotations

import pandas as pd


class _ReadsMixin:
    """Read operations for POStore. Requires self._conn() from BaseSQLiteStore."""

    def _get_metadata(self, po_number: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT *, (SELECT SUM(units) FROM po_size_rows WHERE po_number=?) AS total_units "
                "FROM po_metadata WHERE po_number=?",
                (po_number, po_number),
            ).fetchone()
        return dict(row) if row else None

    def list_pos(self, companies: list[str] | None = None) -> pd.DataFrame:
        """Return all stored POs. If companies list given, filter to those only."""
        with self._conn() as conn:
            if companies:
                ph = ",".join("?" * len(companies))
                rows = conn.execute(
                    f"""SELECT m.po_number, m.company, m.style, m.factory, m.country_of_origin,
                              m.xport_date, m.issue_date, m.version,
                              m.division_code, m.division_name, m.source_format,
                              m.file_name, m.extracted_at,
                              COALESCE(SUM(s.units), 0) AS total_units
                       FROM po_metadata m
                       LEFT JOIN po_size_rows s ON s.po_number = m.po_number
                       WHERE m.company IN ({ph})
                       GROUP BY m.po_number
                       ORDER BY m.extracted_at DESC""",
                    companies,
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT m.po_number, m.company, m.style, m.factory, m.country_of_origin,
                              m.xport_date, m.issue_date, m.version,
                              m.division_code, m.division_name, m.source_format,
                              m.file_name, m.extracted_at,
                              COALESCE(SUM(s.units), 0) AS total_units
                       FROM po_metadata m
                       LEFT JOIN po_size_rows s ON s.po_number = m.po_number
                       GROUP BY m.po_number
                       ORDER BY m.extracted_at DESC"""
                ).fetchall()
        cols = ["po_number", "company", "style", "factory", "country_of_origin",
                "xport_date", "issue_date", "version", "division_code",
                "division_name", "source_format", "file_name", "extracted_at", "total_units"]
        return pd.DataFrame([dict(r) for r in rows], columns=cols) if rows else pd.DataFrame(columns=cols)

    def list_history(self, po_number: str) -> pd.DataFrame:
        """All archived versions of a single PO, newest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT version, xport_date, total_units, extracted_at, archived_at, file_name
                   FROM po_version_history WHERE po_number=?
                   ORDER BY archived_at DESC""",
                (po_number,),
            ).fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def load_size_rows(self, po_numbers: list[str]) -> pd.DataFrame:
        if not po_numbers:
            return pd.DataFrame(columns=["PO Number", "Style", "Color", "Size", "Units", "UPC"])
        ph = ",".join("?" * len(po_numbers))
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT po_number, style, color, size, units, upc FROM po_size_rows WHERE po_number IN ({ph})",
                po_numbers,
            ).fetchall()
        if not rows:
            return pd.DataFrame(columns=["PO Number", "Style", "Color", "Size", "Units", "UPC"])
        df = pd.DataFrame([dict(r) for r in rows])
        df.columns = ["PO Number", "Style", "Color", "Size", "Units", "UPC"]
        return df

    def load_metadata(self, po_numbers: list[str]) -> pd.DataFrame:
        if not po_numbers:
            return pd.DataFrame()
        ph = ",".join("?" * len(po_numbers))
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT po_number, company, style, factory, country_of_origin,
                           xport_date, issue_date, version,
                           division_code, division_name, source_format,
                           file_name, extracted_at
                    FROM po_metadata WHERE po_number IN ({ph})""",
                po_numbers,
            ).fetchall()
        return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

    def list_companies(self) -> list[str]:
        """All distinct company names stored in the DB."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT company FROM po_metadata WHERE company IS NOT NULL ORDER BY company"
            ).fetchall()
        return [r[0] for r in rows]

    def list_all_po_styles(self) -> list[str]:
        """All distinct style values from po_metadata."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT style FROM po_metadata "
                "WHERE style IS NOT NULL AND style != '' ORDER BY style"
            ).fetchall()
        return [r[0] for r in rows]

    def list_all_hhn_nos(self) -> list[str]:
        """All distinct hhn_no values stored in style_fabric_parts."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT hhn_no FROM style_fabric_parts "
                "WHERE hhn_no IS NOT NULL AND hhn_no != ''"
            ).fetchall()
        return [r[0] for r in rows]

    def list_all_mapped_styles(self, source: str | None = None) -> list[str]:
        """Distinct style values in style_fabric_parts, optionally filtered by source."""
        clause = "WHERE source = ?" if source else "WHERE style IS NOT NULL AND style != ''"
        params = [source] if source else []
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT DISTINCT style FROM style_fabric_parts {clause} ORDER BY style",
                params,
            ).fetchall()
        return [r[0] for r in rows]

    def delete_pos(self, po_numbers: list[str]) -> int:
        """Delete active PO records.

        BUG-07 fix: version history rows are intentional audit trail and must
        NOT be removed when the active record is deleted.  Deleting history
        made it impossible to recover what had been received/processed.
        """
        if not po_numbers:
            return 0
        ph = ",".join("?" * len(po_numbers))
        with self._conn() as conn:
            n = conn.execute(f"DELETE FROM po_metadata WHERE po_number IN ({ph})", po_numbers).rowcount
            conn.execute(f"DELETE FROM po_size_rows WHERE po_number IN ({ph})", po_numbers)
            # po_version_history rows are preserved — they are the audit trail.
        return n

    def po_count(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM po_metadata").fetchone()[0]
