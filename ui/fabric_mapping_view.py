"""Fabric Mapping tab — per-company style-to-fabric upload and management."""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

from auth.companies import list_company_names, COMPANY_SKY_EAST
from ui.sky_east._shared import _parse_fabric_mapping_bytes
from ui.sky_east.processing import _enrich_fabric_parts_from_cache
from ui.stores import get_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _company_to_source(name: str) -> str:
    """Normalise company display name → DB source string ('Sky East' → 'sky_east')."""
    return re.sub(r'[^a-z0-9]+', '_', name.strip().lower()).strip('_')


@st.cache_data(show_spinner=False)
def _cached_parse_fabric_mapping(file_bytes: bytes) -> dict:
    """Parse fabric mapping bytes; cached so repeated reruns don't re-parse."""
    return _parse_fabric_mapping_bytes(file_bytes)


def _load_mapped_styles(source: str) -> set[str]:
    """Return styles already stored for *source* — resilient to stale cached POStore."""
    store = get_store()
    if hasattr(store, "list_mapped_styles"):
        return store.list_mapped_styles(source)
    with store._conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT style FROM style_fabric_parts WHERE source=?", (source,)
        ).fetchall()
    return {r["style"] for r in rows}


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

def show_fabric_mapping_tab() -> None:
    """Fabric Mapping tab — upload, preview, and manage per-company fabric data."""
    st.subheader("📐 Fabric Mapping")

    # ── Template download ─────────────────────────────────────────────────────
    _hdr_col, _tpl_col = st.columns([3, 1])
    with _hdr_col:
        st.caption(
            "Save style-to-fabric data independently of order processing. "
            "The stored mapping is used by wash labels and buy plans."
        )
    with _tpl_col:
        from po_extractor.ui_helpers.fabric_mapping_template import (
            generate_fabric_mapping_template as _gen_tpl,
        )
        st.download_button(
            "📥 Download Template",
            data=_gen_tpl(),
            file_name="FabricMapping_Template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="fm_tab_tpl_dl",
            use_container_width=True,
        )

    # ── Company selector ──────────────────────────────────────────────────────
    companies = list_company_names(active_only=True)
    default_idx = companies.index(COMPANY_SKY_EAST) if COMPANY_SKY_EAST in companies else 0
    fm_company = st.selectbox(
        "Company / Client",
        companies,
        index=default_idx,
        key="fm_tab_company",
        help="Fabric mappings are stored per company. Select the client this mapping belongs to.",
    )
    source = _company_to_source(fm_company)

    # ── Current stored data summary ───────────────────────────────────────────
    existing_styles = _load_mapped_styles(source)
    if existing_styles:
        st.info(
            f"**{fm_company}** currently has fabric data for **{len(existing_styles)}** "
            f"style(s) stored in the database."
        )
        with st.expander("View stored styles"):
            st.dataframe(
                pd.DataFrame(sorted(existing_styles), columns=["Style"]),
                width="stretch", hide_index=True,
            )
    else:
        st.info(f"No fabric mapping stored yet for **{fm_company}**.")

    st.divider()

    # ── Import mode ───────────────────────────────────────────────────────────
    import_mode = st.radio(
        "Import mode",
        ["Upsert — update existing + add new",
         "Add new only — skip styles already in DB",
         "Replace all — clear existing first, then import"],
        key="fm_tab_mode",
        help=(
            "**Upsert**: each style in the file overwrites whatever is stored for that style.  \n"
            "**Add new only**: styles already in the DB are left unchanged.  \n"
            "**Replace all**: ALL existing fabric data for this company is deleted before import."
        ),
    )

    # ── File upload ───────────────────────────────────────────────────────────
    fm_file = st.file_uploader(
        "Style-Fabric mapping file",
        type=["xlsx", "xls"],
        key="fm_tab_uploader",
        label_visibility="collapsed",
    )

    if not fm_file:
        return

    # ── Parse & classify ──────────────────────────────────────────────────────
    try:
        style_parts_map = _cached_parse_fabric_mapping(fm_file.getvalue())
    except Exception as exc:
        st.error(f"Could not parse file: {exc}")
        return

    if not style_parts_map:
        st.warning(
            "No valid style rows found in the file. "
            "Check that the header row matches the template format."
        )
        return

    # Classify each style in the file
    preview_rows = []
    n_new = n_update = n_skip = 0
    for style, parts in sorted(style_parts_map.items()):
        valid_parts = [p for p in parts if p.hhn_no]
        if not valid_parts:
            status = "⚠️ No fabric codes"
            n_skip += 1
        elif style in existing_styles:
            status = "♻️ Will update"
            n_update += 1
        else:
            status = "🆕 New"
            n_new += 1
        preview_rows.append({
            "Style":        style,
            "Fabric Codes": len(valid_parts),
            "Status":       status,
        })

    # ── Preview ───────────────────────────────────────────────────────────────
    st.markdown(f"**Preview — {fm_file.name}**")
    mc = st.columns(3)
    mc[0].metric("🆕 New styles",          n_new)
    mc[1].metric("♻️ Will update",          n_update)
    mc[2].metric("⚠️ Skipped (no codes)",  n_skip)

    with st.expander("Show full style list", expanded=(len(preview_rows) <= 20)):
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

    # ── Confirmation for Replace all ─────────────────────────────────────────
    confirmed_replace = True
    if "Replace all" in import_mode:
        st.warning(
            f"⚠️ **Replace all** will permanently delete ALL existing fabric data for "
            f"**{fm_company}** ({len(existing_styles)} style(s)) before importing. "
            "This cannot be undone."
        )
        confirmed_replace = st.checkbox(
            "I understand — delete existing data and replace with this file",
            key="fm_tab_replace_confirm",
        )

    # ── Import button ─────────────────────────────────────────────────────────
    import_disabled = (not confirmed_replace) or (n_new + n_update == 0)
    if st.button(
        "💾 Import Fabric Mapping", type="primary",
        key="fm_tab_import_btn",
        disabled=import_disabled,
    ):
        with st.spinner("Saving fabric mapping..."):
            try:
                store = get_store()

                if "Replace all" in import_mode:
                    deleted = store.delete_fabric_parts(source)
                    st.caption(f"Deleted {deleted} existing fabric part(s) for {fm_company}.")
                    to_save = style_parts_map
                elif "Add new only" in import_mode:
                    to_save = {s: p for s, p in style_parts_map.items()
                               if s not in existing_styles}
                    skipped_n = len(style_parts_map) - len(to_save)
                    if skipped_n:
                        st.caption(f"Skipped {skipped_n} existing style(s).")
                else:  # Upsert
                    to_save = style_parts_map

                if not to_save:
                    st.warning("Nothing to import after applying the selected mode.")
                else:
                    store.save_fabric_parts_batch(source, to_save)
                    _enrich_fabric_parts_from_cache(to_save)
                    n_styles = len(to_save)
                    n_parts  = sum(len(v) for v in to_save.values())
                    st.success(
                        f"✅ Saved **{n_parts}** fabric part(s) across "
                        f"**{n_styles}** style(s) for **{fm_company}**."
                    )
                    _cached_parse_fabric_mapping.clear()

            except Exception as exc:
                st.error(f"Import failed: {exc}")
