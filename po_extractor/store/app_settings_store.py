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
KEY_DEEPSEEK_API_KEY     = "deepseek_api_key"
KEY_EXTRACTION_METHOD    = "extraction_method"   # "regex" | "deepseek" | "auto"
KEY_DEEPSEEK_MODEL       = "deepseek_model"
KEY_COLOR_AI_ENHANCE     = "color_ai_enhance_mode"   # "local" | "local_ai_enhance"
KEY_MASK_USE_AI          = "mask_use_ai"         # "true" | "false" — AI-assist price masking
KEY_CPRS_BASE_URL        = "cprs_base_url"       # CPRS knowledge-base API base URL
KEY_CPRS_API_KEY         = "cprs_api_key"        # CPRS x-api-key
KEY_CPRS_SHOW_ADDRESS    = "cprs_show_address"   # "true" | "false" — show host in sidebar status
# "true" | "false" — let the AI decide whether a retyped colour on a re-imported
# Sky East contract is the same item, when plain normalisation says it is not.
KEY_ITEM_COLOUR_AI_MATCH = "item_colour_ai_match"


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
    KEY_EXTRACTION_METHOD:    "regex",      # "regex" | "deepseek"
    KEY_DEEPSEEK_MODEL:       "deepseek-chat",
    KEY_DEEPSEEK_API_KEY:     "",
    KEY_COLOR_AI_ENHANCE:     "local",      # "local" | "local_ai_enhance"
    KEY_MASK_USE_AI:          "false",      # "true" | "false"
    KEY_CPRS_BASE_URL:        "",           # e.g. http://localhost:3100
    KEY_CPRS_API_KEY:         "",
    KEY_CPRS_SHOW_ADDRESS:    "false",       # hide the host in the sidebar by default
    KEY_ITEM_COLOUR_AI_MATCH: "false",      # opt-in — normalisation alone runs by default
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
                # OR IGNORE: two processes starting together both see the
                # migration as pending; the loser's insert must be a silent
                # no-op, not a UNIQUE-constraint crash on startup.
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings_migrations (name) "
                    "VALUES (?)", (name,)
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
