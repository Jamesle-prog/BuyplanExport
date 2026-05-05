"""Exception-queue mixin for POStore."""
from __future__ import annotations

from datetime import datetime

import pandas as pd


class _ExceptionsMixin:
    """Exception queue operations for POStore. Requires self._conn() from BaseSQLiteStore."""

    def save_exception(self, po_number: str, file_name: str, company: str,
                       reason: str, processed_by: str = "") -> None:
        """Record a parse or save exception in the exception queue."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO po_exceptions
                   (po_number, file_name, company, status, reason, created_at, updated_at, processed_by)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (po_number, file_name, company, "pending", reason, now, now, processed_by),
            )

    def list_exceptions(self, companies: list[str] | None = None) -> pd.DataFrame:
        """Return all exceptions, optionally filtered by company list."""
        with self._conn() as conn:
            if companies:
                ph = ",".join("?" * len(companies))
                rows = conn.execute(
                    f"SELECT * FROM po_exceptions WHERE company IN ({ph}) ORDER BY created_at DESC",
                    companies,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM po_exceptions ORDER BY created_at DESC"
                ).fetchall()
        cols = ["id", "po_number", "file_name", "company", "status",
                "reason", "raw_text_snippet", "created_at", "updated_at", "processed_by"]
        return pd.DataFrame([dict(r) for r in rows], columns=cols) if rows else pd.DataFrame(columns=cols)

    def update_exception_status(self, exc_id: int, status: str) -> None:
        """Update the status of an exception record."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                "UPDATE po_exceptions SET status=?, updated_at=? WHERE id=?",
                (status, now, exc_id),
            )
