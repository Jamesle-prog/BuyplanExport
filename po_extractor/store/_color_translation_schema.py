"""Schema DDL, migration SQL, column-alias sets, and helpers for ColorTranslationStore."""
from __future__ import annotations

_SCHEMA = """
CREATE TABLE IF NOT EXISTS color_translations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client        TEXT    NOT NULL,
    brand         TEXT    NOT NULL DEFAULT '',
    en_color      TEXT    NOT NULL,
    cn_color      TEXT,
    color_code    TEXT,
    light_or_dark TEXT    DEFAULT '',   -- 'light' / 'dark' / '' (unknown)
    label_color   TEXT    DEFAULT '',   -- 主标颜色 — '黑色' / '白色' / ''
    notes         TEXT,
    updated_at    TEXT,
    UNIQUE(client, brand, en_color)
);

CREATE INDEX IF NOT EXISTS idx_ct_client ON color_translations(client);
CREATE INDEX IF NOT EXISTS idx_ct_brand  ON color_translations(brand);
CREATE INDEX IF NOT EXISTS idx_ct_en     ON color_translations(en_color);
"""

_MIGRATION_ADD_BRAND = """
ALTER TABLE color_translations RENAME TO color_translations_v1;

CREATE TABLE color_translations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    client        TEXT    NOT NULL,
    brand         TEXT    NOT NULL DEFAULT '',
    en_color      TEXT    NOT NULL,
    cn_color      TEXT,
    color_code    TEXT,
    light_or_dark TEXT    DEFAULT '',
    label_color   TEXT    DEFAULT '',
    notes         TEXT,
    updated_at    TEXT,
    UNIQUE(client, brand, en_color)
);

INSERT INTO color_translations
    (id, client, brand, en_color, cn_color, color_code, light_or_dark, label_color, notes, updated_at)
SELECT id, client, '', en_color, cn_color, color_code, '', '', notes, updated_at
FROM color_translations_v1;

DROP TABLE color_translations_v1;

CREATE INDEX IF NOT EXISTS idx_ct_client ON color_translations(client);
CREATE INDEX IF NOT EXISTS idx_ct_brand  ON color_translations(brand);
CREATE INDEX IF NOT EXISTS idx_ct_en     ON color_translations(en_color);
"""

# Migration applied when the table already has 'brand' but is missing the
# new light_or_dark / label_color columns (v1 → v2).
_MIGRATION_ADD_LABEL_COLS = """
ALTER TABLE color_translations ADD COLUMN light_or_dark TEXT DEFAULT '';
ALTER TABLE color_translations ADD COLUMN label_color   TEXT DEFAULT '';
"""

# Audit-log table: every change (insert / update / delete) to a row in
# color_translations is recorded here so users can review who changed what
# and when in the Admin UI.
_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS color_translations_audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    action       TEXT    NOT NULL,        -- 'insert' | 'update' | 'delete'
    row_id       INTEGER,                 -- color_translations.id when known
    client       TEXT    NOT NULL DEFAULT '',
    brand        TEXT    NOT NULL DEFAULT '',
    en_color     TEXT    NOT NULL DEFAULT '',
    field        TEXT    NOT NULL DEFAULT '',  -- column name, or '*' for whole row
    old_value    TEXT,
    new_value    TEXT,
    changed_at   TEXT    NOT NULL,
    changed_by   TEXT    NOT NULL DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_cta_changed_at ON color_translations_audit(changed_at);
CREATE INDEX IF NOT EXISTS idx_cta_client_brand ON color_translations_audit(client, brand);
CREATE INDEX IF NOT EXISTS idx_cta_en_color ON color_translations_audit(en_color);
"""

# Column alias sets for Excel import (case-insensitive)
_COL_CLIENT     = {"client", "客户", "brand_client", "公司"}
_COL_BRAND      = {"brand", "品牌", "brand name", "brand_name"}
_COL_EN_COLOR   = {"en_color", "english color", "english", "颜色英文", "color (en)", "color"}
_COL_CN_COLOR   = {"cn_color", "chinese color", "chinese", "颜色中文", "color (cn)", "中文颜色"}
_COL_COLOR_CODE = {"color_code", "color code", "code", "颜色代码"}
_COL_LIGHT_DARK = {"light_or_dark", "light/dark", "light_dark", "shade",
                   "color shade", "颜色明暗", "深浅"}
_COL_LABEL_CLR  = {"label_color", "label color", "main label color",
                   "主标颜色", "主标色"}
_COL_NOTES      = {"notes", "备注", "remark"}


def _v(val) -> str:
    return "" if val is None else str(val).strip()


def _match_col(header: str, aliases: set[str]) -> bool:
    return header.lower().strip() in aliases
