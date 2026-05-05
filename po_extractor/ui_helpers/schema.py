"""Live output schema (editable JSON store)."""
from __future__ import annotations

import json
import os

from po_extractor.output_schema import LABEL


def schema_seed_rows() -> list[dict]:
    """Convert static OUTPUT_FIELDS into flat dicts for the JSON store."""
    from po_extractor.output_schema import OUTPUT_FIELDS as _OF
    rows = []
    for f in _OF:
        rows.append({
            "db_col":   f["db_col"],
            "label":    f["label"],
            "sky_east": f["client_alias"].get("sky_east", ""),
            "infor":    f["client_alias"].get("infor", ""),
            "legacy":   f["client_alias"].get("legacy", ""),
            "required": f["required"],
            "notes":    f["notes"],
        })
    return rows


def load_live_schema(schema_path: str) -> list[dict]:
    """Return schema rows from JSON; seeds file from code defaults on first run."""
    if os.path.exists(schema_path):
        with open(schema_path, encoding="utf-8") as fh:
            return json.load(fh)
    rows = schema_seed_rows()
    save_live_schema(schema_path, rows)
    return rows


def save_live_schema(schema_path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(schema_path) or ".", exist_ok=True)
    with open(schema_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)


def live_label_for(rows: list[dict], db_col: str, fallback: str | None = None) -> str:
    """Return the current user-configured standard label for a DB column."""
    for row in rows:
        if row.get("db_col") == db_col:
            return row.get("label") or fallback or db_col
    return LABEL.get(db_col, fallback or db_col)


def live_client_label_for(rows: list[dict], db_col: str, client: str) -> str:
    """Return the client-specific alias for db_col (falls back to live label)."""
    for row in rows:
        if row.get("db_col") == db_col:
            return row.get(client, "") or live_label_for(rows, db_col)
    return live_label_for(rows, db_col)
