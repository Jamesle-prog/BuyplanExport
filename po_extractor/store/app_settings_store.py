"""SQLite-backed key-value store for application-level admin settings.

Schema
------
app_settings(
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    updated_by TEXT
)
"""
from __future__ import annotations

from datetime import datetime, timezone

from .base_store import BaseSQLiteStore

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT,
    updated_by TEXT
);
"""

# Hard-coded fallback used when no DB row exists for a key.
_DEFAULTS: dict[str, str] = {
    "default_color_source": "progress",   # "db" | "progress"
}


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class AppSettingsStore(BaseSQLiteStore):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ── Read ────────────────────────────────────────────────────────────────

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the stored value for *key*, or *default* if not set.

        Falls back to the built-in ``_DEFAULTS`` dict before returning
        *default* so callers don't need to know the hard-coded fallback.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        if row:
            return row["value"]
        return _DEFAULTS.get(key, default)

    def get_all(self) -> dict[str, str]:
        """Return all stored settings as a plain dict."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key, value FROM app_settings"
            ).fetchall()
        stored = {r["key"]: r["value"] for r in rows}
        # Merge with defaults so callers always see every known key.
        return {**_DEFAULTS, **stored}

    # ── Write ───────────────────────────────────────────────────────────────

    def set(self, key: str, value: str, *, updated_by: str = "") -> None:
        """Upsert *key* → *value*."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at, updated_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value      = excluded.value,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (key, value, now, updated_by),
            )
