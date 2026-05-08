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
# Setting keys (single source of truth — import from here, never re-type)
# ---------------------------------------------------------------------------

KEY_DEFAULT_COLOR_SOURCE = "default_color_source"


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
CREATE TABLE IF NOT EXISTS app_settings_migrations (
    name TEXT PRIMARY KEY
);
"""

# One-time data migrations applied at store init.
# Each entry: (migration_name, SQL to execute).
# A migration runs exactly once — when its name is absent from
# app_settings_migrations.  After that the admin can freely override the
# value without it being reset on the next restart.
_ONE_TIME_MIGRATIONS: list[tuple[str, str]] = [
    (
        "color_default_to_progress",
        f"INSERT OR REPLACE INTO app_settings (key, value) "
        f"VALUES ('{KEY_DEFAULT_COLOR_SOURCE}', 'progress')",
    ),
]

# Hard-coded fallback used when no DB row exists for a key.
_DEFAULTS: dict[str, str] = {
    KEY_DEFAULT_COLOR_SOURCE: "progress",   # "db" | "progress"
}


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class AppSettingsStore(BaseSQLiteStore):
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            # Run any pending one-time migrations.  Single SELECT to fetch all
            # already-applied names — avoids one SQL call per migration entry.
            done = {
                row[0] for row in conn.execute(
                    "SELECT name FROM app_settings_migrations"
                ).fetchall()
            }
            for name, sql in _ONE_TIME_MIGRATIONS:
                if name in done:
                    continue
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO app_settings_migrations (name) VALUES (?)", (name,)
                )

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
