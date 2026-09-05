"""SQLite-backed store for UI translation strings.

Stores English text → per-language translations so the interface can be
displayed in any supported language without touching Python source.

Schema
------
ui_translations(
    id          INTEGER PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,   -- English text used as stable key
    en_text     TEXT NOT NULL DEFAULT '',
    zh_text     TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '', -- "label"|"button"|"header"|"message"|"caption"
    module      TEXT NOT NULL DEFAULT '', -- "shared"|"giii"|"sky_east"|"admin"|"summary"
    updated_at  TEXT,
    updated_by  TEXT
)
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from .base_store import BaseSQLiteStore, current_actor

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ui_translations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    NOT NULL UNIQUE,
    en_text     TEXT    NOT NULL DEFAULT '',
    zh_text     TEXT    NOT NULL DEFAULT '',
    category    TEXT    NOT NULL DEFAULT '',
    module      TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT,
    updated_by  TEXT
);
CREATE INDEX IF NOT EXISTS idx_uit_module   ON ui_translations(module);
CREATE INDEX IF NOT EXISTS idx_uit_category ON ui_translations(category);
"""

# Supported language codes → column name in ui_translations.
_LANG_COL: dict[str, str] = {
    "zh": "zh_text",
}

# Seed rows live in _ui_translation_seed.py (data only); _SEED keeps the
# name the Admin → Translations page counts.
from ._ui_translation_seed import SEED as _SEED


_current_actor = current_actor


class UITranslationStore(BaseSQLiteStore):
    """SQLite-backed store for UI translation strings.

    Keys are the English text strings used throughout the UI.  For each key
    the store holds one translation column per supported language (currently
    only ``zh_text``).  Additional language columns can be added via schema
    migrations without breaking existing code.
    """

    def __init__(self, db_path: str | Path):
        self._init_db(db_path, mkdir=True)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _setup_schema(self, conn) -> None:
        conn.executescript(_SCHEMA)

    # ── Seed ──────────────────────────────────────────────────────────────────

    def seed_defaults(self, skip_existing: bool = True) -> dict[str, int]:
        """Insert built-in translations.  Skips rows already present by default.

        Returns ``{"inserted": N, "updated": N, "skipped": N}``.
        """
        now = datetime.now(timezone.utc).isoformat()
        inserted = updated = skipped = 0
        with self._conn() as conn:
            for key, zh_text, category, module in _SEED:
                exists = conn.execute(
                    "SELECT id FROM ui_translations WHERE key=?", (key,)
                ).fetchone()
                if exists:
                    if skip_existing:
                        skipped += 1
                        continue
                    conn.execute(
                        """UPDATE ui_translations
                           SET zh_text=?, category=?, module=?,
                               updated_at=?, updated_by='seed'
                           WHERE key=?""",
                        (zh_text, category, module, now, key),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """INSERT INTO ui_translations
                               (key, en_text, zh_text, category, module,
                                updated_at, updated_by)
                           VALUES (?,?,?,?,?,?,?)""",
                        (key, key, zh_text, category, module, now, "seed"),
                    )
                    inserted += 1
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    # ── Upsert / write ────────────────────────────────────────────────────────

    def upsert(self, key: str, en_text: str, zh_text: str,
               category: str = "", module: str = "",
               actor: str | None = None) -> None:
        """Insert or update a single translation row."""
        now   = datetime.now(timezone.utc).isoformat()
        by    = actor or _current_actor()
        en    = en_text.strip()
        clean = key.strip()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO ui_translations
                       (key, en_text, zh_text, category, module, updated_at, updated_by)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET
                       en_text=excluded.en_text,
                       zh_text=excluded.zh_text,
                       category=excluded.category,
                       module=excluded.module,
                       updated_at=excluded.updated_at,
                       updated_by=excluded.updated_by""",
                (clean, en, zh_text.strip(), category, module, now, by),
            )

    def upsert_many(self, rows: list[dict],
                    skip_existing: bool = False) -> dict[str, int]:
        """Bulk-upsert a list of dicts with keys ``key, en_text, zh_text,
        category, module``.  Returns ``{"inserted": N, "updated": N, "skipped": N}``.
        """
        now = datetime.now(timezone.utc).isoformat()
        by = _current_actor()
        inserted = updated = skipped = 0
        with self._conn() as conn:
            for row in rows:
                key = str(row.get("key", "") or "").strip()
                if not key:
                    continue
                exists = conn.execute(
                    "SELECT id FROM ui_translations WHERE key=?", (key,)
                ).fetchone()
                if exists and skip_existing:
                    skipped += 1
                    continue
                conn.execute(
                    """INSERT INTO ui_translations
                           (key, en_text, zh_text, category, module,
                            updated_at, updated_by)
                       VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(key) DO UPDATE SET
                           en_text=excluded.en_text,
                           zh_text=excluded.zh_text,
                           category=excluded.category,
                           module=excluded.module,
                           updated_at=excluded.updated_at,
                           updated_by=excluded.updated_by""",
                    (key,
                     str(row.get("en_text", key)).strip(),
                     str(row.get("zh_text", "") or "").strip(),
                     str(row.get("category", "") or ""),
                     str(row.get("module",   "") or ""),
                     now, by),
                )
                if exists:
                    updated += 1
                else:
                    inserted += 1
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    def delete_ids(self, ids: list[int]) -> int:
        """Delete rows by primary key.  Returns count deleted."""
        clean = [int(i) for i in ids if i is not None]
        if not clean:
            return 0
        ph = ",".join("?" * len(clean))
        with self._conn() as conn:
            cur = conn.execute(
                f"DELETE FROM ui_translations WHERE id IN ({ph})", clean
            )
        return cur.rowcount

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """Return all rows as list of dicts."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ui_translations "
                "ORDER BY module, category, key"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_by_module(self, module: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ui_translations WHERE module=? "
                "ORDER BY category, key",
                (module,),
            ).fetchall()
        return [dict(r) for r in rows]

    def build_lookup(self, lang: str) -> dict[str, str]:
        """Return ``{key: translated_text}`` for the given language.

        Falls back to English (key itself) for missing translations.
        Only returns rows where the translation column is non-empty.
        """
        col = _LANG_COL.get(lang)
        if not col:
            return {}
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT key, {col} FROM ui_translations WHERE {col} != ''"
            ).fetchall()
        return {r["key"]: r[col] for r in rows}

    def list_modules(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT module FROM ui_translations ORDER BY module"
            ).fetchall()
        return [r[0] for r in rows if r[0]]

    def list_categories(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM ui_translations ORDER BY category"
            ).fetchall()
        return [r[0] for r in rows if r[0]]

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM ui_translations"
            ).fetchone()[0]

    def count_missing(self, lang: str = "zh") -> int:
        """Count rows where the translation for *lang* is empty."""
        col = _LANG_COL.get(lang, "zh_text")
        with self._conn() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM ui_translations WHERE {col}=''"
            ).fetchone()[0]

    # ── Import / Export ───────────────────────────────────────────────────────

    def to_csv(self) -> str:
        """Export all translations as a UTF-8 CSV string."""
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=["key", "en_text", "zh_text", "category", "module"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(self.get_all())
        return buf.getvalue()

    def import_csv(self, csv_text: str,
                   skip_existing: bool = False) -> dict[str, int]:
        """Import translations from a CSV string.  Returns upsert counts."""
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        return self.upsert_many(rows, skip_existing=skip_existing)

    def to_dataframe(self):
        """Return all rows as a pandas DataFrame (for admin data_editor)."""
        import pandas as pd
        rows = self.get_all()
        cols = ["id", "key", "en_text", "zh_text", "category", "module",
                "updated_at", "updated_by"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows)[
            [c for c in cols if c in rows[0]]
        ]
