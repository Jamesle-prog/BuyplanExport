"""Unified buy-plan template configuration registry.

A single source of truth for the configurable Excel templates each pipeline
uses.  Each *pipeline* has:

    - A pipeline_id (stable string used by the admin UI)
    - A display name shown to admins
    - Optional template .xlsx file (read/write through this module)
    - A JSON config file (read/write through this module)

Templates and configs live under ``data/buyplan_templates/``.  GIII uses
``{client}.xlsx`` + ``{client}_config.json`` per company (handled directly by
``buyplan_export``).  Sky East uses fixed-name files (``Sky_East.xlsx`` etc.)
and reads its overrides from this module.

Schema (all keys optional; missing keys fall back to exporter defaults):
    {
      "header_row":      int,                 # 1-based; row where data starts -1
      "data_start_row":  int,                 # 1-based; first data row
      "write_headers":   bool,
      "column_map":      {logical_field: column_letter_or_int},
      "size_column_map": {size_label:    column_letter_or_int},
      "meta_column_map": {meta_field:    column_letter_or_int},
      "fabric_slots":    [{"row": int,
                           "body_part": col, "hhn": col, "key": col}, …],
      "fabric_key_field": "display_key" | "composition",
      "placeholders":    [str, …],            # advisory only
      "notes":           str
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from auth.companies import COMPANY_GIII, COMPANY_SKY_EAST

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA_DIR      = Path(__file__).parent.parent.parent / "data"
_TEMPLATES_DIR = _DATA_DIR / "buyplan_templates"


# ---------------------------------------------------------------------------
# Pipeline registry
# ---------------------------------------------------------------------------
@dataclass
class Pipeline:
    pipeline_id:   str           # stable id, e.g. "sky_east_buyplan"
    display_name:  str           # shown in admin UI
    company:       str           # company this pipeline belongs to
    template_file: str | None    # filename under _TEMPLATES_DIR, or None if no template
    config_file:   str           # JSON config filename under _TEMPLATES_DIR
    description:   str           # admin-facing help text
    supports_fabric_slots: bool = False


_PIPELINES: list[Pipeline] = [
    Pipeline(
        pipeline_id="sky_east_buyplan",
        display_name="Sky East — Buy Plan",
        company=COMPANY_SKY_EAST,
        template_file="Sky_East.xlsx",
        config_file="Sky_East_config.json",
        description=(
            "Per-style buy plan workbook (Template sheet). "
            "Data block, fabric header rows, and Q5 style-total cell are configurable."
        ),
        supports_fabric_slots=True,
    ),
    Pipeline(
        pipeline_id="sky_east_nukuryou",
        display_name="Sky East — 核料 (Nukuryou)",
        company=COMPANY_SKY_EAST,
        template_file="Sky_East_P.xlsx",
        config_file="Sky_East_P_config.json",
        description=(
            "Per-fabric workbook listing colour rows by size. "
            "Configure colour column and per-size columns."
        ),
        supports_fabric_slots=False,
    ),
    Pipeline(
        pipeline_id="giii_buyplan_default",
        display_name="GIII — Buy Plan (Default Template)",
        company=COMPANY_GIII,
        template_file="default.xlsx",
        config_file="default_config.json",
        description=(
            "Shared GIII fallback template. "
            "Per-client overrides live alongside as `{client}.xlsx` + `{client}_config.json`."
        ),
        supports_fabric_slots=False,
    ),
]


def list_pipelines() -> list[Pipeline]:
    """Return the registered pipelines (in display order)."""
    return list(_PIPELINES)


def get_pipeline(pipeline_id: str) -> Pipeline | None:
    return next((p for p in _PIPELINES if p.pipeline_id == pipeline_id), None)


# ---------------------------------------------------------------------------
# Config IO
# ---------------------------------------------------------------------------
_DEFAULT_CFG: dict = {
    "header_row":       None,
    "data_start_row":   None,
    "write_headers":    False,
    "column_map":       {},
    "size_column_map":  {},
    "meta_column_map":  {},
    "fabric_slots":     [],
    "fabric_key_field": "display_key",
    "placeholders":     [],
    "notes":            "",
}


def _config_path(pipeline_id: str) -> Path:
    p = get_pipeline(pipeline_id)
    if p is None:
        raise KeyError(f"Unknown pipeline: {pipeline_id}")
    _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return _TEMPLATES_DIR / p.config_file


def _template_path(pipeline_id: str) -> Path | None:
    p = get_pipeline(pipeline_id)
    if p is None or not p.template_file:
        return None
    _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return _TEMPLATES_DIR / p.template_file


def load_config(pipeline_id: str) -> dict:
    """Return the merged config dict for *pipeline_id*.

    Missing keys are filled from ``_DEFAULT_CFG``.  Unknown pipelines raise.
    """
    cfg = dict(_DEFAULT_CFG)
    path = _config_path(pipeline_id)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            # Corrupt JSON — fall back to defaults rather than crashing exports
            pass
    return cfg


def save_config(pipeline_id: str, cfg: dict) -> Path:
    """Validate and persist *cfg* for *pipeline_id*.  Returns the file path."""
    path = _config_path(pipeline_id)
    cleaned = _validate_config(cfg)
    path.write_text(
        json.dumps(cleaned, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def template_exists(pipeline_id: str) -> bool:
    p = _template_path(pipeline_id)
    return bool(p and p.exists())


def read_template_bytes(pipeline_id: str) -> bytes:
    p = _template_path(pipeline_id)
    if not p or not p.exists():
        raise FileNotFoundError(f"No template installed for pipeline {pipeline_id}")
    return p.read_bytes()


def write_template_bytes(pipeline_id: str, xlsx_bytes: bytes) -> Path:
    p = _template_path(pipeline_id)
    if not p:
        raise ValueError(f"Pipeline {pipeline_id} has no template slot")
    p.write_bytes(xlsx_bytes)
    return p


# ---------------------------------------------------------------------------
# Validation / coercion
# ---------------------------------------------------------------------------
def _col_to_int(v) -> int:
    """Accept either a 1-based int or an Excel column letter."""
    if isinstance(v, int):
        return max(1, v)
    if isinstance(v, str) and v.strip():
        s = v.strip().upper()
        if s.isdigit():
            return max(1, int(s))
        n = 0
        for ch in s:
            if not ("A" <= ch <= "Z"):
                raise ValueError(f"Invalid column letter: {v!r}")
            n = n * 26 + (ord(ch) - 64)
        return max(1, n)
    raise ValueError(f"Cannot interpret column value: {v!r}")


def _validate_config(cfg: dict) -> dict:
    """Coerce inputs and drop unknown top-level keys.

    Column letters are kept as letters in storage (more readable when the
    JSON is opened by hand), but exporters get integers via
    :func:`column_letter_to_int`.
    """
    out = dict(_DEFAULT_CFG)
    if not isinstance(cfg, dict):
        return out

    for k in ("header_row", "data_start_row"):
        v = cfg.get(k)
        if v not in (None, "", 0):
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                pass

    if isinstance(cfg.get("write_headers"), bool):
        out["write_headers"] = cfg["write_headers"]

    for k in ("column_map", "size_column_map", "meta_column_map"):
        m = cfg.get(k) or {}
        if isinstance(m, dict):
            out[k] = {str(kk): _coerce_col(vv) for kk, vv in m.items() if vv not in (None, "")}

    slots = cfg.get("fabric_slots") or []
    if isinstance(slots, list):
        cleaned_slots = []
        for s in slots:
            if not isinstance(s, dict):
                continue
            try:
                cleaned_slots.append({
                    "row":       int(s.get("row") or 0),
                    "body_part": _coerce_col(s.get("body_part")) if s.get("body_part") not in (None, "") else "",
                    "hhn":       _coerce_col(s.get("hhn")) if s.get("hhn") not in (None, "") else "",
                    "key":       _coerce_col(s.get("key")) if s.get("key") not in (None, "") else "",
                })
            except Exception:
                pass
        out["fabric_slots"] = [s for s in cleaned_slots if s["row"] > 0]

    fkf = cfg.get("fabric_key_field")
    if fkf in ("display_key", "composition"):
        out["fabric_key_field"] = fkf

    if isinstance(cfg.get("notes"), str):
        out["notes"] = cfg["notes"]
    if isinstance(cfg.get("placeholders"), list):
        out["placeholders"] = [str(x) for x in cfg["placeholders"]]

    return out


def _coerce_col(v) -> str:
    """Return the value as a column letter string for storage."""
    if isinstance(v, str) and v.strip():
        # Accept either letters or digits; normalise to letters
        s = v.strip().upper()
        if s.isdigit():
            return column_letter_from_int(int(s))
        return s
    if isinstance(v, int):
        return column_letter_from_int(v)
    return ""


# ---------------------------------------------------------------------------
# Public letter ↔ int conversion (used by exporters)
# ---------------------------------------------------------------------------
def column_letter_to_int(s: str | int) -> int:
    return _col_to_int(s)


def column_letter_from_int(n: int) -> str:
    n = max(1, int(n))
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def coerce_column_map(m: dict | None) -> dict[str, int]:
    """Convert a stored {field: letter} map to {field: int_col}."""
    if not m:
        return {}
    out: dict[str, int] = {}
    for k, v in m.items():
        try:
            out[str(k)] = column_letter_to_int(v)
        except Exception:
            pass
    return out
