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

    _EXC_COLS = ["id", "po_number", "file_name", "company", "status",
                 "reason", "raw_text_snippet", "created_at", "updated_at",
                 "processed_by"]

    def list_exceptions(self, companies: list[str] | None = None) -> pd.DataFrame:
        """Return all exceptions, optionally filtered by company list.

        *companies*: ``None`` scopes to everything (admin); a list scopes to
        exactly those, and an EMPTY list to nothing.
        """
        rows: list = []
        with self._conn() as conn:
            # `companies is not None` -- an EMPTY list means the caller has no
            # company access and must see nothing. Testing the list for truth
            # instead treated that as "no filter", which showed an unassigned
            # account every company's rows. See auth.users.company_scope.
            if companies is not None and not companies:
                pass                       # no access -> no rows
            elif companies is not None:
                ph = ",".join("?" * len(companies))
                rows = conn.execute(
                    f"SELECT * FROM po_exceptions WHERE company IN ({ph}) ORDER BY created_at DESC",
                    companies,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM po_exceptions ORDER BY created_at DESC"
                ).fetchall()
        cols = self._EXC_COLS
        return pd.DataFrame([dict(r) for r in rows], columns=cols) if rows else pd.DataFrame(columns=cols)

    def exception_ids(self, companies: list[str] | None = None) -> set[int]:
        """The exception ids *companies* may act on — same scoping rules as
        :meth:`list_exceptions`. Used to check an id BEFORE writing to it,
        since the id arrives from the browser and need not be one that was
        ever displayed."""
        df = self.list_exceptions(companies)
        return set() if df.empty else {int(i) for i in df["id"]}

    def update_exception_status(self, exc_id: int, status: str) -> None:
        """Update the status of an exception record.

        Does NOT check company access — callers reaching this from a user
        action must confirm the id against :meth:`exception_ids` first.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                "UPDATE po_exceptions SET status=?, updated_at=? WHERE id=?",
                (status, now, exc_id),
            )
