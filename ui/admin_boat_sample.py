"""Admin panel — 船样要求 (Shipping Sample Requirements), every company.

The editor itself lives in :mod:`ui.boat_sample_view`, which also backs the
📐 Reference Data → 🚢 船样要求 section that any user can reach for their own
companies. This panel is the same tool with the company list unrestricted, so
the two can't drift apart.

Companies come from auth.companies.list_company_names(); brands from
ui.stores.list_all_brands() (colour translations ∪ brands already registered
for a requirement, including those auto-added when Sky East orders load).
"""
from __future__ import annotations

import streamlit as st

from auth.companies import list_company_names
from ui.boat_sample_view import render_boat_sample_editor
from ui.i18n import t


def show_boat_sample_admin() -> None:
    st.markdown(f"#### 🚢 {t('船样要求')} {t('管理')}")
    st.caption(t(
        "Specify the shipping-sample requirement text per **Company / Brand**. "
        "The value is written into the 船样要求 column of every matching data "
        "row in the Sky East buy plan at export time."
    ))
    st.caption("👥 " + t(
        "Users can maintain their own company's entries themselves under "
        "📐 Reference Data → 🚢 船样要求. This panel covers every company."
    ))

    companies = list_company_names(active_only=True) or []
    if not companies:
        st.info(t("No active companies registered yet — add one under "
                  "Admin → Companies first."))
        return
    render_boat_sample_editor(companies, key_prefix="bsr_admin")
