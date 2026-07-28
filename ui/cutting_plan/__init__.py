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

    # NOT st.tabs — it runs every section on every render, and each of these
    # loads its own data (Sky East items for the PO pickers, the saved-plan
    # list with its per-plan detail, the standard-output demand matrices).
    # Opening this tab was paying for all three to show one.
    _sections = [
        (f"📤 {t('Upload & Link')}",    show_upload_section),
        (f"📋 {t('Saved plans')}",      show_plans_section),
        (f"📄 {t('Standard output')}",  show_standard_section),
    ]
    _labels = [lbl for lbl, _ in _sections]
    _key = "cp_section_nav"
    if st.session_state.get(_key) not in _labels:      # language toggle
        st.session_state[_key] = _labels[0]
    _active = st.segmented_control(
        t("Section"), _labels, key=_key, label_visibility="collapsed")
    if _active not in _labels:
        _active = st.session_state[_key]
    _sections[_labels.index(_active)][1]()


__all__ = ["show_cutting_plan_tab"]
