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


# Fields compared between the stored FabricPart and the incoming one, in
# display order.
_DIFF_FIELDS = [
    ("body_part",   "Body Part"),
    ("hhn_no",      "HHN No."),
    ("composition", "Composition"),
    ("weight_gsm",  "Weight (gsm)"),
    ("width_cm",    "Width (cm)"),
]


def _diff_fabric_parts(
    old_parts: list, new_parts: list, *, will_delete_missing: bool,
) -> list[dict]:
    """Field-level diff between the stored and incoming parts of one style.

    Matched by ``(combo_idx, seq)`` — stable slot positions assigned at parse
    time (see ``fabric_mapping_parse.py``), so slot 1 in the old data lines up
    with slot 1 in the new file even when other slots were skipped.  Returns
    one row per changed field, plus one row for an entirely added/removed
    combo/seq slot. Empty list means the stored data already matches the file.

    ``will_delete_missing`` must reflect what the *import* actually does with
    a stored slot absent from the new file: ``save_fabric_parts_batch()`` is
    an ``INSERT ... ON CONFLICT DO UPDATE`` — it never deletes rows. So a
    slot missing from the file is only truly removed under **Replace all**
    (which wipes the style's data first); under Upsert / Add new only it is
    left in the database untouched. Mislabeling this as "removed" when it
    will actually persist would be a data-loss surprise in the wrong
    direction — the user would think it's gone when it isn't.
    """
    old_map = {(p.combo_idx, p.seq): p for p in old_parts}
    new_map = {(p.combo_idx, p.seq): p for p in new_parts}
    rows: list[dict] = []
    for combo, seq in sorted(set(old_map) | set(new_map)):
        op = old_map.get((combo, seq))
        npart = new_map.get((combo, seq))
        if op is None:
            rows.append({"Combo": combo, "Seq": seq, "Field": "(new fabric slot)",
                        "Stored": "—", "In File": npart.display()})
            continue
        if npart is None:
            if will_delete_missing:
                rows.append({"Combo": combo, "Seq": seq, "Field": "(slot removed)",
                            "Stored": op.display(), "In File": "—"})
            else:
                rows.append({"Combo": combo, "Seq": seq,
                            "Field": "(not in file — kept, not deleted)",
                            "Stored": op.display(), "In File": "(unchanged)"})
            continue
        for attr, label in _DIFF_FIELDS:
            ov, nv = getattr(op, attr), getattr(npart, attr)
            if ov != nv:
                rows.append({"Combo": combo, "Seq": seq, "Field": label,
                            "Stored": ov or "—", "In File": nv or "—"})
    return rows


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

def show_fabric_mapping_tab() -> None:
    """📐 Fabric Mapping tab — style-to-fabric mapping and HHN Contract Progress.

    Both sub-sections follow the same upload-once / diff-on-update pattern:
    save data independently of order processing so it doesn't need
    re-uploading for every run.
    """
    st.subheader("📐 Fabric Mapping")

    fm_tab, pm_tab = st.tabs(["🧵 Style-Fabric Mapping", "📋 HHN Contract Progress (大货进度表)"])
    with fm_tab:
        _show_fabric_mapping_section()
    with pm_tab:
        from ui.progress_mapping_view import show_progress_mapping_section
        show_progress_mapping_section()


def _show_fabric_mapping_section() -> None:
    """Style-Fabric mapping — upload, preview, and manage per-company fabric data."""
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

    # ── Duplicate-combo health check ──────────────────────────────────────────
    with st.expander("🩺 Check for duplicate fabric mapping data"):
        st.caption(
            "Scans **all companies** for styles whose fabric combo is stored "
            "identically twice under different combo numbers — a leftover from "
            "an import that saw the same style row more than once. Left alone, "
            "each duplicate combo produces an extra, identical sheet in exports "
            "that iterate one sheet per combo (e.g. the Sky East Buy Plan)."
        )
        if st.button("🔍 Scan for duplicates", key="fm_tab_dup_scan"):
            st.session_state["fm_tab_dup_results"] = get_store().find_duplicate_fabric_combos()

        dup_results = st.session_state.get("fm_tab_dup_results")
        if dup_results is not None:
            if not dup_results:
                st.success("✅ No duplicate fabric combos found.")
            else:
                n_styles = len({(d["source"], d["style"]) for d in dup_results})
                st.warning(
                    f"⚠️ Found **{len(dup_results)}** duplicate combo group(s) "
                    f"across **{n_styles}** style(s)."
                )
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Source": d["source"], "Style": d["style"],
                            "Keep Combo": d["keep_combo_idx"],
                            "Remove Combo(s)": ", ".join(str(c) for c in d["remove_combo_idx"]),
                            "Fabric": d["parts_preview"],
                        }
                        for d in dup_results
                    ]),
                    width="stretch", hide_index=True,
                )
                if st.button(
                    "🧹 Remove all duplicate combos shown above",
                    type="primary", key="fm_tab_dup_cleanup",
                ):
                    dstore = get_store()
                    n_deleted = 0
                    for d in dup_results:
                        for cidx in d["remove_combo_idx"]:
                            n_deleted += dstore.delete_fabric_combo(
                                d["source"], d["style"], cidx
                            )
                    st.success(f"Removed {n_deleted} duplicate fabric part row(s).")
                    st.session_state["fm_tab_dup_results"] = None
                    st.rerun()

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

    # ── Classify each style in the file ───────────────────────────────────────
    # Existing styles are diffed against stored data up front so "Will update"
    # means "content actually differs" — not just "this style already exists
    # in the DB". Upsert re-writes every matching row regardless of whether
    # anything differs, but a status of "Will update" when nothing would
    # actually change is misleading (see: 2026-07-01 duplicate-combo report,
    # where a style still showed "Will update" after the only real difference
    # — a stale duplicate combo — had already been cleaned up).
    will_delete_missing = "Replace all" in import_mode
    existing_in_file = [s for s in style_parts_map if s in existing_styles]
    old_parts_map = (
        get_store().load_fabric_parts_for_styles(existing_in_file, source)
        if existing_in_file else {}
    )

    new_rows, changed_rows, unchanged_rows, skip_rows = [], [], [], []
    diff_by_style: dict[str, list[dict]] = {}
    for style, parts in sorted(style_parts_map.items()):
        valid_parts = [p for p in parts if p.hhn_no]
        row = {"Style": style, "Fabric Codes": len(valid_parts)}
        if not valid_parts:
            row["Status"] = "⚠️ No fabric codes"
            skip_rows.append(row)
        elif style in existing_styles:
            diff = _diff_fabric_parts(
                old_parts_map.get(style, []), valid_parts,
                will_delete_missing=will_delete_missing,
            )
            diff_by_style[style] = diff
            if diff:
                row["Status"] = "♻️ Will update"
                changed_rows.append(row)
            else:
                row["Status"] = "✓ Up to date"
                unchanged_rows.append(row)
        else:
            row["Status"] = "🆕 New"
            new_rows.append(row)

    preview_rows = new_rows + changed_rows + unchanged_rows + skip_rows
    n_new, n_update, n_same, n_skip = (
        len(new_rows), len(changed_rows), len(unchanged_rows), len(skip_rows)
    )

    # ── Preview ───────────────────────────────────────────────────────────────
    st.markdown(f"**Preview — {fm_file.name}**")
    mc = st.columns(4)
    mc[0].metric("🆕 New styles",         n_new)
    mc[1].metric("♻️ Will update",         n_update)
    mc[2].metric("✓ Already up to date",  n_same)
    mc[3].metric("⚠️ Skipped (no codes)", n_skip)

    with st.expander("Show full style list", expanded=(len(preview_rows) <= 20)):
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

    # ── Diff for styles that will update ─────────────────────────────────────
    if existing_in_file and "Add new only" in import_mode:
        # These styles already exist, so Add-new-only skips them entirely —
        # a diff here would suggest changes that will not actually happen.
        with st.expander(f"🔍 {len(existing_in_file)} existing style(s) — will be skipped"):
            st.caption(
                "Import mode is **Add new only**: styles already in the database are "
                "left completely unchanged. None of these will be touched by this import."
            )
    elif changed_rows or unchanged_rows:
        diff_rows = [
            {"Style": style, **d}
            for style in (r["Style"] for r in changed_rows)
            for d in diff_by_style[style]
        ]
        with st.expander(
            f"🔍 Show differences for updating styles "
            f"({n_update} of {n_update + n_same} actually changed)",
            expanded=(0 < len(diff_rows) <= 30),
        ):
            if diff_rows:
                st.dataframe(pd.DataFrame(diff_rows), width="stretch", hide_index=True)
                if not will_delete_missing and any(
                    d["Field"].startswith("(not in file") for d in diff_rows
                ):
                    st.caption(
                        "💡 **(not in file — kept, not deleted)** rows stay in the database "
                        "as-is under Upsert. Use **Replace all** if you need stale fabric "
                        "slots actually removed."
                    )
            else:
                st.caption(
                    "No field-level differences — the stored data already matches the file."
                )

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
    # n_same ("already up to date") still counts toward "something valid to
    # import" — Upsert/Replace all writing identical data is a harmless no-op,
    # and Replace all specifically is how a duplicate-combo style gets fixed
    # even when its content otherwise matches the file.
    import_disabled = (not confirmed_replace) or (n_new + n_update + n_same == 0)
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
