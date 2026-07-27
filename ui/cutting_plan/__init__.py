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

    flash = st.session_state.pop(SK.CP_FLASH, None)
    if flash:
        kind, message = flash
        getattr(st, kind, st.info)(message)

    tab_upload, tab_plans, tab_std = st.tabs(
        [f"📤 {t('Upload & Link')}", f"📋 {t('Saved plans')}",
         f"📄 {t('Standard output')}"])

    with tab_upload:
        show_upload_section()
    with tab_plans:
        show_plans_section()
    with tab_std:
        show_standard_section()


__all__ = ["show_cutting_plan_tab"]
