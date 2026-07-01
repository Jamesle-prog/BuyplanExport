"""HHN Contract Progress (大货进度表) tab — per-company upload and management.

Mirrors ui/fabric_mapping_view.py's upload/preview/import/diff pattern, but
for 大货进度表 rows instead of style-fabric mappings: upload once, save
persistently, and every Sky East run / buy plan afterward automatically uses
the saved data instead of requiring the file to be re-uploaded every time.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from auth.companies import list_company_names, COMPANY_SKY_EAST
from po_extractor.lookups.progress_lookup import parse_progress_rows, _norm_key
from po_extractor.store._po_store_progress import _DB_TO_RECORD
from ui.fabric_mapping_view import _company_to_source
from ui.stores import get_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _cached_parse_progress(file_bytes: bytes) -> list[dict]:
    """Parse 大货进度表 bytes; cached so repeated reruns don't re-parse."""
    return parse_progress_rows(file_bytes)


def _record_key(rec: dict) -> tuple[str, str, str]:
    """Return the (pc_no_norm, style_norm, color_norm) identity key for a
    parsed record — matches how the persistent store identifies a row.
    """
    return (_norm_key(rec.get("pc_no") or ""), rec.get("style") or "", rec.get("color_norm") or "")


# Fields compared between the stored DB row and the incoming record, in
# display order. Keys are the parser's record-shape names (see
# progress_lookup.parse_progress_rows / po_store_progress._DB_TO_RECORD).
_DIFF_FIELDS = [
    ("contract_no", "Contract No."),
    ("color",       "Color (EN)"),
    ("cn_color",    "Color (CN)"),
    ("color_code",  "Color Code"),
    ("label_color", "Label Color"),
    ("ex_fty",      "Ex-Fty"),
    ("qty",         "Qty"),
    ("zalando_po",  "PO#"),
    ("brand",       "Brand"),
    ("fabric",      "Fabric Detail"),
    ("test_note",       "测试"),
    ("color_summary",   "色汇总"),
    ("launch_date",     "Launch Date"),
    ("remarks",         "备注"),
]


def _diff_progress_record(old_db_row: dict, new_record: dict) -> list[dict]:
    """Field-level diff between a stored DB row and the incoming record.

    Unlike Fabric Mapping's Upsert (which never deletes a stale slot),
    ``save_progress_records_batch()`` is also an upsert — but every field on
    a matched row IS overwritten unconditionally (there's no "missing field
    stays untouched" case here, since the whole row is one contract line,
    not a set of independent slots). So every differing field shown here
    will actually change on import, regardless of import mode.
    """
    old_record = {
        rec_key: (old_db_row.get(db_col) or "")
        for db_col, rec_key in _DB_TO_RECORD.items()
    }
    rows: list[dict] = []
    for key, label in _DIFF_FIELDS:
        ov = str(old_record.get(key, "") or "")
        nv = str(new_record.get(key, "") or "")
        if ov != nv:
            rows.append({"Field": label, "Stored": ov or "—", "In File": nv or "—"})
    return rows


# ---------------------------------------------------------------------------
# Main section
# ---------------------------------------------------------------------------

def show_progress_mapping_section() -> None:
    """HHN Contract Progress — upload, preview, and manage per-company data."""
    st.caption(
        "Save 大货进度表 (HHN Contract Progress) data independently of order "
        "processing. Upload once here — every Sky East run and buy plan "
        "afterward automatically uses the saved data, no need to re-upload "
        "the same file every time. Pictures are not stored (text data only)."
    )

    # ── Company selector ───────────────────────────────────────────────────
    companies = list_company_names(active_only=True)
    default_idx = companies.index(COMPANY_SKY_EAST) if COMPANY_SKY_EAST in companies else 0
    pm_company = st.selectbox(
        "Company / Client",
        companies,
        index=default_idx,
        key="pm_tab_company",
        help="Progress data is stored per company. Select the client this file belongs to.",
    )
    source = _company_to_source(pm_company)
    store = get_store()

    # ── Current stored data summary ────────────────────────────────────────
    existing_count = store.count_progress_records(source)
    if existing_count:
        st.info(
            f"**{pm_company}** currently has **{existing_count}** progress "
            f"record(s) stored in the database."
        )
        with st.expander("View stored records"):
            records = store.load_progress_records(source)
            df = pd.DataFrame(records)
            show_cols = [c for c in
                        ["contract_no", "pc_no", "style_display", "brand",
                         "color", "cn_color", "color_code", "ex_fty", "zalando_po"]
                        if c in df.columns]
            st.dataframe(
                df[show_cols].rename(columns={
                    "contract_no": "Contract No.", "pc_no": "PC No.",
                    "style_display": "Style", "brand": "Brand",
                    "color": "Color (EN)", "cn_color": "Color (CN)",
                    "color_code": "Color Code", "ex_fty": "Ex-Fty",
                    "zalando_po": "PO#",
                }),
                width="stretch", hide_index=True,
            )
    else:
        st.info(f"No progress data stored yet for **{pm_company}**.")

    st.divider()

    # ── Import mode ─────────────────────────────────────────────────────────
    import_mode = st.radio(
        "Import mode",
        ["Upsert — update existing + add new",
         "Add new only — skip records already in DB",
         "Replace all — clear existing first, then import"],
        key="pm_tab_mode",
        help=(
            "**Upsert**: each row in the file overwrites whatever is stored for "
            "that (PC No. · Style · Color) combination.  \n"
            "**Add new only**: combinations already in the DB are left unchanged.  \n"
            "**Replace all**: ALL existing progress data for this company is "
            "deleted before import."
        ),
    )

    # ── File upload ─────────────────────────────────────────────────────────
    pm_file = st.file_uploader(
        "HHN Contract Progress file (大货进度表)",
        type=["xlsx", "xls"],
        key="pm_tab_uploader",
        label_visibility="collapsed",
    )

    if not pm_file:
        return

    # ── Parse & classify ────────────────────────────────────────────────────
    try:
        records = _cached_parse_progress(pm_file.getvalue())
    except Exception as exc:
        st.error(f"Could not parse file: {exc}")
        return

    if not records:
        st.warning(
            "No valid rows found in the file. "
            "Check that the header row matches the expected 大货进度表 format."
        )
        return

    existing_keys = store.list_progress_keys(source)
    keyed_records = [(rec, _record_key(rec)) for rec in records]
    existing_in_file = [(rec, key) for rec, key in keyed_records if key in existing_keys]
    old_db_rows = (
        store.get_progress_records_by_keys(source, [key for _, key in existing_in_file])
        if existing_in_file else {}
    )

    new_rows, changed_rows, unchanged_rows, skip_rows = [], [], [], []
    diff_by_key: dict[tuple, list[dict]] = {}
    for rec, key in keyed_records:
        row = {
            "PC No.": rec.get("pc_no", ""), "Style": rec.get("style_display", ""),
            "Color": rec.get("color", ""), "Contract No.": rec.get("contract_no", ""),
        }
        if not key[1]:   # no style_norm — shouldn't happen (parser requires style)
            row["Status"] = "⚠️ No style"
            skip_rows.append(row)
        elif key in existing_keys:
            diff = _diff_progress_record(old_db_rows.get(key, {}), rec)
            diff_by_key[key] = diff
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

    # ── Preview ──────────────────────────────────────────────────────────────
    st.markdown(f"**Preview — {pm_file.name}**")
    mc = st.columns(4)
    mc[0].metric("🆕 New records",       n_new)
    mc[1].metric("♻️ Will update",        n_update)
    mc[2].metric("✓ Already up to date", n_same)
    mc[3].metric("⚠️ Skipped",           n_skip)

    with st.expander("Show full record list", expanded=(len(preview_rows) <= 20)):
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)

    # ── Diff for records that will update ────────────────────────────────────
    if existing_in_file and "Add new only" in import_mode:
        with st.expander(f"🔍 {len(existing_in_file)} existing record(s) — will be skipped"):
            st.caption(
                "Import mode is **Add new only**: records already in the database "
                "are left completely unchanged. None of these will be touched by "
                "this import."
            )
    elif changed_rows or unchanged_rows:
        diff_rows = [
            {"PC No.": rec.get("pc_no", ""), "Style": rec.get("style_display", ""),
             "Color": rec.get("color", ""), **d}
            for rec, key in existing_in_file
            if key in diff_by_key
            for d in diff_by_key[key]
        ]
        with st.expander(
            f"🔍 Show differences for updating records "
            f"({n_update} of {n_update + n_same} actually changed)",
            expanded=(0 < len(diff_rows) <= 30),
        ):
            if diff_rows:
                st.dataframe(pd.DataFrame(diff_rows), width="stretch", hide_index=True)
            else:
                st.caption(
                    "No field-level differences — the stored data already matches the file."
                )

    # ── Confirmation for Replace all ─────────────────────────────────────────
    confirmed_replace = True
    if "Replace all" in import_mode:
        st.warning(
            f"⚠️ **Replace all** will permanently delete ALL existing progress data "
            f"for **{pm_company}** ({existing_count} record(s)) before importing. "
            "This cannot be undone."
        )
        confirmed_replace = st.checkbox(
            "I understand — delete existing data and replace with this file",
            key="pm_tab_replace_confirm",
        )

    # ── Import button ─────────────────────────────────────────────────────────
    import_disabled = (not confirmed_replace) or (n_new + n_update + n_same == 0)
    if st.button(
        "💾 Import Progress Data", type="primary",
        key="pm_tab_import_btn",
        disabled=import_disabled,
    ):
        with st.spinner("Saving progress data..."):
            try:
                if "Replace all" in import_mode:
                    deleted = store.delete_progress_records(source)
                    st.caption(f"Deleted {deleted} existing record(s) for {pm_company}.")
                    to_save = records
                elif "Add new only" in import_mode:
                    to_save = [rec for rec, key in keyed_records if key not in existing_keys]
                    skipped_n = len(records) - len(to_save)
                    if skipped_n:
                        st.caption(f"Skipped {skipped_n} existing record(s).")
                else:  # Upsert
                    to_save = records

                if not to_save:
                    st.warning("Nothing to import after applying the selected mode.")
                else:
                    n_saved = store.save_progress_records_batch(source, to_save)
                    st.success(
                        f"✅ Saved **{n_saved}** progress record(s) for **{pm_company}**."
                    )
                    _cached_parse_progress.clear()

            except Exception as exc:
                st.error(f"Import failed: {exc}")
