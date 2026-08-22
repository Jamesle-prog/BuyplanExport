"""Admin: Company registry view."""
from __future__ import annotations

import streamlit as st
from ui.shared import delete_button

from ui.i18n import t
from auth.companies import (
    delete_company, list_companies, upsert_company,
    COMPANY_GIII, COMPANY_SKY_EAST,
)

# Core companies that cannot be deleted from the UI.
_PROTECTED = (COMPANY_GIII, COMPANY_SKY_EAST)


def show_company_admin() -> None:
    st.subheader(t("Company Registry"))
    st.caption(t("Companies are pre-seeded. Add new clients here when on-boarding them."))

    cos = list_companies(active_only=False)
    for co in cos:
        active = co.get("active", True)
        label = (
            f"{'✅' if active else '❌'} {co['name']}  |  {co['display_name']}  |  "
            f"formats: {', '.join(co.get('formats', []))}"
        )
        with st.expander(label):
            c1, c2 = st.columns(2)
            with c1:
                new_display = st.text_input(
                    t("Display name"), value=co.get("display_name", co["name"]),
                    key=f"co_disp_{co['name']}",
                )
                new_sheet = st.text_input(
                    t("Excel sheet name"), value=co.get("excel_sheet") or "",
                    key=f"co_sheet_{co['name']}",
                )
                new_formats = st.text_input(
                    t("Format IDs (comma-separated)"),
                    value=", ".join(co.get("formats", [])),
                    key=f"co_fmts_{co['name']}",
                )
                new_ftypes = st.text_input(
                    t("File types (pdf, excel)"),
                    value=", ".join(co.get("file_types", [])),
                    key=f"co_ft_{co['name']}",
                )
            with c2:
                new_color = st.color_picker(
                    t("Badge colour"), value=co.get("color", "#888888"),
                    key=f"co_col_{co['name']}",
                )
                new_active = st.checkbox(
                    t("Active"), value=active, key=f"co_act_{co['name']}",
                )

            btn_c1, btn_c2 = st.columns(2)
            with btn_c1:
                if st.button(f"💾 {t('Save')}", key=f"co_save_{co['name']}"):
                    upsert_company(
                        name=co["name"],
                        display_name=new_display,
                        file_types=[f.strip() for f in new_ftypes.split(",") if f.strip()],
                        formats=[f.strip() for f in new_formats.split(",") if f.strip()],
                        excel_sheet=new_sheet or None,
                        color=new_color,
                        active=new_active,
                    )
                    st.success(t("Saved."))
                    st.rerun()
            with btn_c2:
                if co["name"] not in _PROTECTED:
                    if delete_button(t("Delete"), key=f"co_del_{co['name']}"):
                        delete_company(co["name"])
                        st.success(f"{t('Deleted')} {co['name']}.")
                        st.rerun()

    st.divider()
    st.markdown(f"**{t('Add new company')}**")
    nc1, nc2, nc3 = st.columns(3)
    with nc1:
        new_co_name = st.text_input(t("Name (unique key)"), key="new_co_name")
    with nc2:
        new_co_display = st.text_input(t("Display name"), key="new_co_display")
    with nc3:
        new_co_ftype = st.selectbox(
            t("Primary file type"), ["pdf", "excel"], key="new_co_ftype",
        )
    if st.button(f"➕ {t('Add company')}", type="primary", key="add_co"):
        if new_co_name:
            upsert_company(
                name=new_co_name.strip(),
                display_name=new_co_display or new_co_name.strip(),
                file_types=[new_co_ftype],
                formats=["excel_zalando" if new_co_ftype == "excel" else "infor_nexus"],
                excel_sheet="1.1.PO_Client" if new_co_ftype == "excel" else None,
            )
            st.success(f"{t('Company')} '{new_co_name}' {t('added.')}")
            st.rerun()
