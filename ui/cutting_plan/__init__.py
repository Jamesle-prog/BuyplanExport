"""Cutting Plan tab (✂️ 裁剪计划).

Separate top-level module, gated by ``auth.users.MODULE_CUTTING_PLAN``: cut
plans expose marker efficiency, fabric consumption and material cost, so
access is granted explicitly and is *not* implied by any Sky East module.

Three screens:
  * **Upload & Link** — read an externally-produced cut plan and record which
    PO(s) it covers (a plan routinely covers several).
  * **Saved plans**   — browse, re-link, re-download, delete.
  * **Standard output** — pick PO(s), get the plan in the house layout with
    quantities rebuilt from the PO.
"""
from __future__ import annotations

import streamlit as st
from ui.shared import lazy_sections, show_flash

from ui.i18n import t
from ui.session_keys import SK


def show_cutting_plan_tab() -> None:
    """Public entry point for the Cutting Plan tab."""
    from ui.cutting_plan.upload import show_upload_section
    from ui.cutting_plan.plans import show_plans_section
    from ui.cutting_plan.standard import show_standard_section

    st.subheader(t("Cutting Plan"))
    st.caption(t(
        "Cut plans are produced by the marker software outside this app. "
        "Upload one here to link it to the PO(s) it covers, then export any "
        "PO's plan in one standard layout."
    ))

    show_flash(SK.CP_FLASH)

    # One section rendered at a time: each loads its own data (Sky East items
    # for the PO pickers, the saved-plan list, the demand matrices), so
    # building all three to show one is real cost. lazy_sections carries the
    # rerun- and language-toggle handling that used to be duplicated here.
    lazy_sections([
        (f"📤 {t('Upload & Link')}",    show_upload_section),
        (f"📋 {t('Saved plans')}",      show_plans_section),
        (f"📄 {t('Standard output')}",  show_standard_section),
    ], key=SK.CP_SECTION_NAV)


__all__ = ["show_cutting_plan_tab"]
