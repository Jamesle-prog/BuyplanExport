"""Persistent company registry with pre-seeded defaults.

Each company record stores:
  name          — unique key (string)
  display_name  — human label
  file_types    — list: "pdf", "excel"
  formats       — list of internal format identifiers the company uses
  excel_sheet   — sheet name to look for in Excel files (optional)
  color         — hex for UI badge (optional)
  active        — bool, soft-delete

Use the module-level constants (COMPANY_GIII, COMPANY_SKY_EAST) everywhere a
company name string is needed — never hardcode the literals directly.
"""
import json
import os

_COMPANIES_FILE = os.path.join(os.path.dirname(__file__), "companies.json")

# ── Canonical company-name constants ─────────────────────────────────────────
# Import these wherever a company name string is needed instead of using
# raw string literals, so a rename only requires changing this file.
COMPANY_GIII      = "GIII"
COMPANY_SKY_EAST  = "Sky East"

# Normalised source identifiers used as the 'source' column in style_fabric_parts.
# Derived from the company name via _company_to_source(); defined here so all
# modules can import a single constant instead of repeating the string.
SOURCE_GIII      = "giii"
SOURCE_SKY_EAST  = "sky_east"

# Companies that existed in older installs but are no longer used.
_REMOVED_COMPANIES = ("DKNY", "Zalando")

# ── Default companies seeded on first run ─────────────────────────────────────
_DEFAULTS: list[dict] = [
    {
        "name": COMPANY_GIII,
        "display_name": "G-III Apparel Group",
        "file_types": ["pdf"],
        "formats": ["infor_nexus", "legacy_giii"],
        "excel_sheet": None,
        "color": "#1f77b4",
        "active": True,
    },
    {
        "name": COMPANY_SKY_EAST,
        "display_name": "Sky East",
        "file_types": [],
        "formats": [],
        "excel_sheet": None,
        "color": "#2ca02c",
        "active": True,
    },
]

# Map internal format id → list of company names that use it (for reverse lookup)
FORMAT_TO_COMPANIES: dict[str, list[str]] = {
    "infor_nexus": [COMPANY_GIII],
    "legacy_giii": [COMPANY_GIII],
}


def _load() -> dict[str, dict]:
    if not os.path.exists(_COMPANIES_FILE):
        data = {c["name"]: c for c in _DEFAULTS}
        _save(data)
        return data
    with open(_COMPANIES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict[str, dict]) -> None:
    with open(_COMPANIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Public API ─────────────────────────────────────────────────────────────────

def list_companies(active_only: bool = True) -> list[dict]:
    """Return all company records, optionally filtered to active only."""
    data = _load()
    records = list(data.values())
    if active_only:
        records = [r for r in records if r.get("active", True)]
    return sorted(records, key=lambda r: r["name"])


def list_company_names(active_only: bool = True) -> list[str]:
    return [c["name"] for c in list_companies(active_only)]


def get_company(name: str) -> dict | None:
    return _load().get(name)


def upsert_company(
    name: str,
    display_name: str | None = None,
    file_types: list[str] | None = None,
    formats: list[str] | None = None,
    excel_sheet: str | None = None,
    color: str | None = None,
    active: bool | None = None,
) -> None:
    data = _load()
    existing = data.get(name, {})
    # BUG-38 fix: when caller doesn't pass `active`, preserve the existing value
    # rather than defaulting to True — that silently reactivated deactivated
    # companies whenever any other field was edited.  New companies default to
    # active=True only when there's no existing record.
    if active is None:
        resolved_active = existing.get("active", True)
    else:
        resolved_active = active
    data[name] = {
        "name": name,
        "display_name": display_name or existing.get("display_name", name),
        "file_types": file_types if file_types is not None else existing.get("file_types", ["pdf"]),
        "formats": formats if formats is not None else existing.get("formats", []),
        "excel_sheet": excel_sheet if excel_sheet is not None else existing.get("excel_sheet"),
        "color": color or existing.get("color", "#888888"),
        "active": resolved_active,
    }
    _save(data)


def deactivate_company(name: str) -> None:
    data = _load()
    if name in data:
        data[name]["active"] = False
        _save(data)


def delete_company(name: str) -> None:
    data = _load()
    data.pop(name, None)
    _save(data)


def companies_for_format(fmt: str) -> list[str]:
    """Return company names that handle the given format id."""
    data = _load()
    return [
        c["name"] for c in data.values()
        if c.get("active", True) and fmt in c.get("formats", [])
    ]


def ensure_defaults_seeded() -> None:
    """Idempotently seed default companies and remove retired ones (call at app startup)."""
    data = _load()
    changed = False
    # Add any missing defaults
    for default in _DEFAULTS:
        if default["name"] not in data:
            data[default["name"]] = default
            changed = True
    # Remove companies that are no longer supported
    for name in _REMOVED_COMPANIES:
        if name in data:
            del data[name]
            changed = True
    if changed:
        _save(data)
