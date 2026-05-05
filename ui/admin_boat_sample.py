"""Admin panel — 船样要求 (Boat Sample Requirements) management.

Company and brand lists are sourced from the live data dictionaries:
  • Companies → auth.companies.list_company_names()
  • Brands     → ColorTranslationStore.list_brands(client=company)

The stored requirement text is injected into column P (船样要求) of every
Sky East buy-plan data row whose brand matches during export.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from auth.companies import list_company_names
from ui.stores import get_boat_sample_store, list_all_brands


def show_boat_sample_admin() -> None:
    st.markdown("#### 🚢 船样要求 管理")
    st.caption(
        "Specify the boat-sample requirement text per **Company / Brand**. "
        "The value is written into column P (船样要求) of every matching data "
        "row in the Sky East buy plan at export time."
    )

    store = get_boat_sample_store()

    # ── Current records table ─────────────────────────────────────────────────
    rows = store.list_all()
    st.markdown("##### Existing requirements")
    if rows:
        df = pd.DataFrame(rows, columns=["company", "brand", "req_text", "updated_at"])
        df.columns = ["Company", "Brand", "Requirement Text", "Last Updated"]
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No requirements defined yet.")

    st.divider()

    # ── Data-dictionary sources ───────────────────────────────────────────────
    # Companies come from the Admin → Companies registry (auth layer).
    companies: list[str] = list_company_names(active_only=True) or []

    # ── Add / Edit — cascading company → brand dropdowns ─────────────────────
    st.markdown("##### Add / Edit requirement")

    # Company selector lives OUTSIDE the form so selecting it reruns the page
    # and the brand list below refreshes immediately.
    selected_company: str = st.selectbox(
        "Company",
        options=companies,
        index=0 if companies else None,
        key="bsr_company_sel",
        help="Select from the companies registered in Admin → Companies.",
    )

    # Single canonical source: list_all_brands() unions ColorTranslationStore
    # and BoatSampleStore so every brand the admin can possibly need to edit
    # shows up — including auto-registered brands inserted when Sky East
    # orders are loaded.
    brands: list[str] = list_all_brands(selected_company) if selected_company else []

    # Surface brands that are registered but still missing requirement text —
    # these are the ones the user came here to fill in.
    pending_rows = [r for r in rows
                    if r.get("company") == selected_company and not (r.get("req_text") or "").strip()]
    if pending_rows:
        _names = ", ".join(f"**{r['brand']}**" for r in pending_rows[:8])
        if len(pending_rows) > 8:
            _names += f" … +{len(pending_rows) - 8} more"
        st.warning(
            f"⏳ {len(pending_rows)} brand(s) under **{selected_company}** still "
            f"need a 船样要求: {_names}",
            icon="⏳",
        )

    if not brands:
        st.caption(
            f"ℹ️ No brands found for **{selected_company}** yet. "
            "Brands will appear here automatically after Sky East orders are "
            "processed (or after color data is imported in Admin → Colors)."
        )

    with st.form("bsr_upsert_form", clear_on_submit=True):
        selected_brand: str = st.selectbox(
            "Brand",
            options=brands,
            index=None,
            placeholder="— select brand —",
            key="bsr_brand_sel",
            help="Includes brands from the color-translation dictionary plus "
                 "any brand already registered for boat-sample requirements "
                 "(e.g. auto-added when Sky East orders are loaded).",
        )
        req_text = st.text_area(
            "Requirement Text (船样要求)",
            placeholder="Enter the boat-sample requirement text…",
            height=100,
            help="This text will be placed in column P of every data row for this brand.",
        )
        submitted = st.form_submit_button("💾 Save", type="primary", use_container_width=True)

    if submitted:
        company_v = (selected_company or "").strip()
        brand_v   = (selected_brand   or "").strip()
        text_v    = (req_text         or "").strip()
        if not company_v:
            st.error("No company selected.")
        elif not brand_v:
            st.error("No brand selected.")
        else:
            store.upsert(company_v, brand_v, text_v)
            if text_v:
                st.success(f"Saved requirement for **{company_v} / {brand_v}**.")
            else:
                st.success(
                    f"Cleared requirement for **{company_v} / {brand_v}** "
                    "(empty text stored — column P will be blank for this brand)."
                )
            st.rerun()

    st.divider()

    # ── Delete ────────────────────────────────────────────────────────────────
    if rows:
        st.markdown("##### Delete requirement")
        options = [f"{r['company']} / {r['brand']}" for r in rows]
        to_delete = st.selectbox(
            "Select entry to delete",
            options,
            index=None,
            placeholder="— choose —",
            key="bsr_del_sel",
        )
        if st.button("🗑️ Delete selected", disabled=not to_delete, key="bsr_del_btn"):
            if to_delete:
                parts = to_delete.split(" / ", 1)
                if len(parts) == 2:
                    n = store.delete(parts[0], parts[1])
                    if n:
                        st.success(f"Deleted: {to_delete}")
                        st.rerun()
                    else:
                        st.warning("Entry not found (already deleted?).")
