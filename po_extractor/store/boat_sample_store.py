"""SQLite store for 船样要求 (boat sample requirements) per (company, brand).

Each row specifies the sample requirement text for one company+brand pair.
The value is injected into column P of Sky East buy-plan data rows during export.
"""
from __future__ import annotations

from datetime import datetime

from .base_store import BaseSQLiteStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS boat_sample_req (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    company     TEXT    NOT NULL,
    brand       TEXT    NOT NULL,
    req_text    TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT,
    UNIQUE (company, brand)
);
"""


# Back-compat shim: the canonical factory lives in po_extractor.store.__init__
# so every store has a uniform import path (`from po_extractor.store import
# get_boat_sample_store`).  This local copy is preserved so old callers
# importing it from this module keep working.
def get_boat_sample_store():
    """Return a BoatSampleStore wired to the canonical DB.

    Prefer ``from po_extractor.store import get_boat_sample_store`` for new
    code — that path is also the one used by ``ui.stores``.
    """
    from . import get_boat_sample_store as _canonical
    return _canonical()


class BoatSampleStore(BaseSQLiteStore):
    """Read/write access to the boat_sample_req table."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_schema()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ── Reads ─────────────────────────────────────────────────────────────────

    def get(self, company: str, brand: str) -> str:
        """Return requirement text for (company, brand), or '' if not set."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT req_text FROM boat_sample_req WHERE company=? AND brand=?",
                (company.strip(), brand.strip()),
            ).fetchone()
        return row["req_text"] if row else ""

    def list_all(self) -> list[dict]:
        """Return all rows ordered by company, brand."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT company, brand, req_text, updated_at
                   FROM boat_sample_req
                   ORDER BY company, brand""",
            ).fetchall()
        return [dict(r) for r in rows]

    def get_batch(self, company: str, brands: list[str]) -> dict[str, str]:
        """Return {brand: req_text} for all matching brands under *company*.

        Brands not found in the DB are absent from the result (not key-with-empty).
        """
        if not brands:
            return {}
        clean_brands = [str(b).strip() for b in brands if b]
        if not clean_brands:
            return {}
        ph = ",".join("?" * len(clean_brands))
        with self._conn() as conn:
            rows = conn.execute(
                f"""SELECT brand, req_text
                    FROM boat_sample_req
                    WHERE company=? AND brand IN ({ph}) AND req_text != ''""",
                [company.strip()] + clean_brands,
            ).fetchall()
        return {r["brand"]: r["req_text"] for r in rows}

    def list_known_brands(self, company: str) -> set[str]:
        """Return the set of brands already registered under *company*
        (regardless of whether their req_text is empty)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT brand FROM boat_sample_req WHERE company=?",
                (company.strip(),),
            ).fetchall()
        return {r["brand"] for r in rows}

    def register_missing_brands(self, company: str, brands: list[str]) -> list[str]:
        """Insert any brand from *brands* that isn't already registered
        under *company* (with empty req_text).  Returns the list of brands
        that were *newly added* (in input order, deduplicated).

        Existing rows are left untouched — their req_text is preserved.
        """
        clean = []
        seen: set[str] = set()
        for b in brands:
            s = str(b or "").strip()
            if s and s not in seen:
                seen.add(s)
                clean.append(s)
        if not clean:
            return []

        existing = self.list_known_brands(company)
        new_brands = [b for b in clean if b not in existing]
        if not new_brands:
            return []

        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO boat_sample_req
                       (company, brand, req_text, updated_at)
                       VALUES (?, ?, '', ?)""",
                [(company.strip(), b, now) for b in new_brands],
            )
        return new_brands

    # ── Writes ────────────────────────────────────────────────────────────────

    def upsert(self, company: str, brand: str, req_text: str) -> None:
        """Insert or update the requirement text for (company, brand)."""
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO boat_sample_req (company, brand, req_text, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(company, brand) DO UPDATE SET
                       req_text   = excluded.req_text,
                       updated_at = excluded.updated_at""",
                (company.strip(), brand.strip(), req_text.strip(), now),
            )

    def delete(self, company: str, brand: str) -> int:
        """Delete record for (company, brand). Returns the number of rows deleted."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM boat_sample_req WHERE company=? AND brand=?",
                (company.strip(), brand.strip()),
            )
        return cur.rowcount
