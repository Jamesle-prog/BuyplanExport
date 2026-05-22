"""Standalone read-only client for the centralised Fabric Master database.

Self-contained — depends only on the Python standard library (sqlite3).
Copy this single file into any application that needs fabric data lookups.

Quick-start
-----------
::
    from fabric_master_client import FabricMasterClient

    # Point at the shared fabric_master.db file
    client = FabricMasterClient(r"C:\\Users\\Administrator\\Desktop\\Tool"
                                r"\\PO_Automation_GIII\\data\\fabric_master.db")

    # Test the connection
    ok, msg = FabricMasterClient.test_connection(client.db_path)
    print(ok, msg)   # True  "OK — 1234 fabric records"

    # Look up a single fabric
    fabric = client.get_by_quality_no("FM-0001")
    # Returns a dict with all columns, or None if not found.

    # Batch look-up (one query, multiple quality_nos / erp_codes)
    batch = client.get_batch_enrichment(["FM-0001", "FM-0002", "HHN-003"])
    # Returns {fabric_no: record_dict, ...}

    # Full-text search
    results = client.search("polyester elastane")
    # Returns list of summary dicts

Configuration
-------------
The path to ``fabric_master.db`` is set in PO_Automation_GIII's Admin
panel under ⚙️ Settings → 🗄 Fabric Master Database, or by the
``FABRIC_DB_PATH`` environment variable, or in
``data/fabric_config.json`` (``fabric_db_path`` key).

To find the current effective path from within PO_Automation_GIII::
    from po_extractor.config import get_fabric_db_path
    print(get_fabric_db_path())
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Summary columns returned by search() / list_all() to keep responses lean.
# ---------------------------------------------------------------------------
_SUMMARY_COLS = (
    "quality_no", "erp_code", "supplier", "composition_en",
    "weight_gsm", "cuttable_width_cm", "dyeing_process",
    "shrinkage_rate", "short_rate", "notes_cn", "display_key",
)


class FabricMasterClient:
    """Read-only access to the centralised fabric master SQLite database.

    Thread-safe: a new SQLite connection is opened and closed for every
    method call (WAL mode allows concurrent readers alongside a writer).
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)

    # ── Connection ─────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA query_only=1")   # enforce read-only at SQLite level
        return conn

    # ── Connection test ────────────────────────────────────────────────────────

    @staticmethod
    def test_connection(db_path: str | Path) -> tuple[bool, str]:
        """Return ``(True, "OK — N records")`` or ``(False, error_message)``.

        Safe to call before instantiating the client — does not modify the DB.
        Uses the same read-only PRAGMAs as ``_conn()`` and closes the
        connection on every code path (including exceptions).
        """
        from contextlib import closing
        try:
            with closing(sqlite3.connect(str(db_path))) as conn:
                conn.execute("PRAGMA query_only=1")
                count = conn.execute(
                    "SELECT COUNT(*) FROM fabric_master"
                ).fetchone()[0]
            return True, f"OK — {count:,} fabric records"
        except Exception as exc:
            return False, str(exc)

    # ── Scalar queries ─────────────────────────────────────────────────────────

    def count(self) -> int:
        """Total number of fabric records."""
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM fabric_master").fetchone()[0]

    def last_import_info(self) -> dict | None:
        """Return ``{"imported_at": str, "source_file": str}`` of the most recent import."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT imported_at, source_file FROM fabric_master "
                "ORDER BY imported_at DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # ── Single-record lookups ─────────────────────────────────────────────────

    def get_by_quality_no(self, quality_no: str) -> dict | None:
        """Return the full record dict, or ``None``.

        Matches by ``quality_no`` first, then by ``erp_code`` (so both the
        company fabric number and the ERP code work as keys).
        """
        key = str(quality_no).strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM fabric_master WHERE quality_no=? OR erp_code=?",
                (key, key),
            ).fetchone()
        return dict(row) if row else None

    def get_key_info(self, fabric_no: str) -> dict | None:
        """Return a lightweight dict with the 6 most-used display fields, or ``None``.

        Fields returned: ``composition_en``, ``weight_gsm``, ``cuttable_width_cm``,
        ``shrinkage_rate``, ``short_rate``, ``notes_cn``.
        """
        key = str(fabric_no).strip()
        with self._conn() as conn:
            row = conn.execute(
                """SELECT composition_en, weight_gsm, cuttable_width_cm,
                          shrinkage_rate, short_rate, notes_cn
                   FROM fabric_master WHERE quality_no=? OR erp_code=?""",
                (key, key),
            ).fetchone()
        return dict(row) if row else None

    def get_display_key(self, fabric_no: str) -> str:
        """Return the composite display key ``quality_no|composition|gsm|width``, or ``""``."""
        key = str(fabric_no).strip()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT display_key FROM fabric_master WHERE quality_no=? OR erp_code=?",
                (key, key),
            ).fetchone()
        return row["display_key"] if row else ""

    # ── Batch lookup ──────────────────────────────────────────────────────────

    def get_batch_enrichment(self, fabric_nos: list[str]) -> dict[str, dict]:
        """Return ``{fabric_no: record}`` for every requested number in one query.

        Tries ``quality_no`` first; any unmatched keys are retried against
        ``erp_code``.  The result dict is keyed by whichever field matched.
        """
        _SQL = (
            "SELECT quality_no, erp_code, display_key, "
            "       composition_en, weight_gsm, cuttable_width_cm, "
            "       shrinkage_rate, short_rate "
            "FROM fabric_master WHERE {col} IN ({ph})"
        )
        keys = list({str(f).strip() for f in fabric_nos if f})
        if not keys:
            return {}

        result: dict[str, dict] = {}
        ph = ",".join("?" * len(keys))
        with self._conn() as conn:
            for row in conn.execute(
                _SQL.format(col="quality_no", ph=ph), keys
            ).fetchall():
                d = dict(row)
                result[d["quality_no"]] = d

            unmatched = [k for k in keys if k not in result]
            if unmatched:
                ph2 = ",".join("?" * len(unmatched))
                for row in conn.execute(
                    _SQL.format(col="erp_code", ph=ph2), unmatched
                ).fetchall():
                    d = dict(row)
                    result[d["erp_code"]] = d

        return result

    # ── Search / browse ───────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 200) -> list[dict]:
        """Full-text search on quality_no, composition_en, supplier, structure_en."""
        q = f"%{str(query).strip()}%"
        cols = ", ".join(_SUMMARY_COLS)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {cols} FROM fabric_master "
                "WHERE quality_no LIKE ? OR composition_en LIKE ? "
                "   OR supplier LIKE ? OR structure_en LIKE ? "
                "ORDER BY quality_no LIMIT ?",
                (q, q, q, q, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all(self, limit: int = 5_000) -> list[dict]:
        """Return up to *limit* records (summary columns only), ordered by quality_no."""
        cols = ", ".join(_SUMMARY_COLS) + ", imported_at, source_file"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {cols} FROM fabric_master ORDER BY quality_no LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_page(self, offset: int = 0, limit: int = 200) -> list[dict]:
        """Return one page of records for paginated UIs."""
        cols = ", ".join(_SUMMARY_COLS) + ", imported_at, source_file"
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT {cols} FROM fabric_master "
                "ORDER BY quality_no LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_all_quality_nos(self) -> list[str]:
        """Return every quality_no value — useful for cross-system orphan checks."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT quality_no FROM fabric_master WHERE quality_no IS NOT NULL"
            ).fetchall()
        return [r[0] for r in rows]
