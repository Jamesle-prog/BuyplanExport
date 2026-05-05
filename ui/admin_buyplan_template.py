"""Back-compat shim — the old single-purpose Buy-Plan Template view.

This module used to host the dedicated GIII per-client buy-plan template UI.
That view has been folded into the unified ``ui/admin_templates.py`` so a single
Admin tab now manages every template (Sky East, GIII per-client, blank samples).

The original symbol ``show_buyplan_template_admin`` is preserved here so any
callers (including tests) keep working without changes.
"""
from __future__ import annotations

from ui.admin_templates import show_templates_admin as _show

# Public re-export — old name → new implementation
show_buyplan_template_admin = _show

__all__ = ["show_buyplan_template_admin"]
