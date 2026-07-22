"""Streamlit view modules — extracted from app.py for separation of concerns.

Each module exports `show_*` functions that render one tab/admin section.
View functions take their app-specific dependencies (paths, cache-clear
callbacks) as parameters to avoid circular imports back into app.py.

Lazy re-exports (PEP 562)
-------------------------
The view modules are pandas/openpyxl/exporter-heavy — importing all of them
costs ~0.6 s. They used to be imported eagerly here, which meant that ANY
``from ui.<submodule> import …`` (e.g. ``from ui.session_keys import SK`` at
the very top of app.py) ran this package ``__init__`` first and dragged the
whole view layer in — so even the logged-out **login page** paid for every
tab it would never draw.

The ``show_*`` names below stay importable as ``from ui import show_…`` (for
back-compat and the view tests), but nothing is imported until the name is
actually accessed. App code imports the concrete submodule lazily inside its
fragment functions, so the login path now touches none of this.
"""
from __future__ import annotations

import importlib

# Public name → the submodule that defines it. Kept explicit (not globbed) so
# the exported surface is greppable and a typo fails loudly.
_LAZY_EXPORTS: dict[str, str] = {
    "show_buyplan_template_admin": "ui.admin_buyplan_template",  # back-compat
    "show_company_admin":          "ui.admin_companies",
    "show_pipeline_layout_admin":  "ui.admin_pipeline_layout",
    "show_schema_editor":          "ui.admin_schema",
    "show_size_order_admin":       "ui.admin_size_order",
    "show_templates_admin":        "ui.admin_templates",
    "show_user_admin":             "ui.admin_users",
    "show_sky_east_tab":           "ui.sky_east_view",
    "show_fabric_db_tab":          "ui.fabric_db_view",
    "show_color_translation_tab":  "ui.color_translation_view",
    "show_smart_upload_tab":       "ui.giii_view",
    "show_summary_tab":            "ui.summary_view",
}

__all__ = list(_LAZY_EXPORTS)


def __getattr__(name: str):
    """Import the defining submodule on first access, then cache the name."""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module 'ui' has no attribute {name!r}")
    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value          # subsequent lookups skip __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
