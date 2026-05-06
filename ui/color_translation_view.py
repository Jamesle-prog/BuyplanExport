"""Color Name Translation tab — EN/CN lookup table by client and brand."""
from __future__ import annotations

import io
import tempfile

import pandas as pd
import streamlit as st

from auth.companies import COMPANY_GIII, COMPANY_SKY_EAST
from ui.shared import XLSX_MIME
from ui.stores import get_color_translation_store

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_CT_COL_CFG = {
    "Delete":        st.column_config.CheckboxColumn(
        "🗑",
        width="small",
        help="Tick rows to delete, then click the **Delete selected** button "
             "below the table.",
        default=False,
    ),
    "Client":        st.column_config.TextColumn("Client", width="small"),
    "Brand":         st.column_config.TextColumn("Brand", width="small"),
    "English Color": st.column_config.TextColumn(
        "English Color",
        width="medium",
        help="Case-insensitive — \"NAVY\", \"navy\", \"Navy\" all collapse "
             "to the same row (stored as title case).",
    ),
    "Chinese Color": st.column_config.TextColumn("Chinese Color (中文颜色)", width="medium"),
    "中文颜色代码":   st.column_config.TextColumn("中文颜色代码", width="small"),
    "Light/Dark":    st.column_config.SelectboxColumn(
        "Light/Dark (深浅)",
        width="small",
        options=["", "light", "dark"],
        help="Whether the body colour is light or dark.  Auto-derived from "
             "the English colour name when left blank — used to pick the "
             "main label colour (light body → 白色, dark body → 黑色).",
    ),
    "Label Color":   st.column_config.SelectboxColumn(
        "Label Color (主标颜色)",
        width="small",
        options=["", "黑色", "白色"],
        help="Main label colour written into column I of the buyplan.  "
             "Auto-derived from Light/Dark when blank: "
             "light → 白色, dark → 黑色.",
    ),
    "Notes":         st.column_config.TextColumn("Notes", width="medium"),
}

_CT_DISPLAY_COLS = ["Delete", "Client", "Brand", "English Color", "Chinese Color",
                    "中文颜色代码", "Light/Dark", "Label Color", "Notes"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ct_excel_template() -> bytes:
    """Return a blank Excel template for bulk color upload."""
    buf = io.BytesIO()
    cols = ["client", "brand", "en_color", "cn_color", "color_code",
            "light_or_dark", "label_color", "notes"]
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        pd.DataFrame(columns=cols).to_excel(
            w, sheet_name="Color Translations", index=False
        )
        ws = w.sheets["Color Translations"]
        for ci, h in enumerate(cols, start=1):
            ws.cell(row=1, column=ci, value=h)
        # Example rows demonstrating the light/dark + label_color rule
        examples = [
            (COMPANY_GIII,     "Karl Lagerfeld", "Black", "黑色", "",     "dark",  "白色", ""),
            (COMPANY_GIII,     "Karl Lagerfeld", "White", "白色", "",     "light", "黑色", ""),
            (COMPANY_SKY_EAST, "Anna Field",     "Navy",  "藏蓝色","52#", "dark",  "白色", ""),
            (COMPANY_SKY_EAST, "Anna Field",     "Cream", "奶白色","92#", "light", "黑色", ""),
        ]
        for ri, row in enumerate(examples, start=2):
            for ci, val in enumerate(row, start=1):
                ws.cell(row=ri, column=ci, value=val)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_color_translation_tab() -> None:
    """Full Color Name Translation table — EN ↔ CN by client + brand."""
    store = get_color_translation_store()
    count = store.count()
    clients = store.list_clients()

    st.subheader("🎨 Color Name Translation")
    st.caption(
        "Reference table mapping English color names to Chinese (中文颜色) by client and brand "
        "(e.g. GIII / Karl Lagerfeld, Sky East / Anna Field). "
        "Use the editor below to add/edit entries, or bulk-import from Excel."
    )

    # Stats bar + quick-load button
    brands_all = store.list_brands()
    m1, m2, m3, m4 = st.columns([1, 1, 1, 2])
    m1.metric("Total entries", f"{count:,}")
    m2.metric("Clients", str(len(clients)))
    m3.metric("Brands", str(len(brands_all)))
    if m4.button("🔄 Load colors from PO database",
                 help=f"Scans all {COMPANY_GIII} PO size rows and {COMPANY_SKY_EAST} items for distinct "
                      "color names and adds any not already in this table. "
                      "Existing Chinese translations are preserved.",
                 use_container_width=True,
                 key="ct_load_from_db"):
        with st.spinner("Scanning PO database for color names…"):
            result = store.load_from_po_data(skip_existing=True)
        ins = result["inserted"]
        skp = result["skipped"]
        src = result["sources"]
        if ins:
            st.success(
                f"Added **{ins}** new color(s) — "
                f"{src['giii']} from {COMPANY_GIII} POs, {src['sky_east']} from {COMPANY_SKY_EAST}. "
                f"{skp} already existed (preserved)."
            )
            st.rerun()
        else:
            st.info(f"No new colors found — all {skp} color(s) were already in the table.")

    # ── Import from a 大货进度表 progress-tracker workbook ───────────────────
    with st.expander("📥 Import from progress tracker (大货进度表)", expanded=False):
        st.caption(
            "Reads the **颜色 / 主标颜色 / 中文颜色** columns (and **BRAND** "
            "when present) from a 大货进度表 workbook and upserts every "
            "unique combination into this table.  English colour names are "
            "case-insensitive — \"NAVY\", \"navy\" and \"Navy\" all collapse "
            "into the same row stored as \"Navy\"."
        )
        prog_file = st.file_uploader(
            "Upload 大货进度表 workbook (.xlsx)",
            type=["xlsx"],
            key="ct_progress_ul",
        )
        prog_client = st.selectbox(
            "Assign rows to client",
            [COMPANY_SKY_EAST, COMPANY_GIII],
            index=0,
            key="ct_progress_client",
            help="Which company should the imported rows be filed under?",
        )
        if prog_file and st.button("▶ Import progress tracker",
                                    key="ct_progress_run", use_container_width=True):
            try:
                tmp = tempfile.mktemp(suffix=".xlsx")
                with open(tmp, "wb") as fh:
                    fh.write(prog_file.read())
                with st.spinner(f"Reading {prog_file.name}…"):
                    result = store.import_from_progress_xlsx(tmp, client=prog_client)
                st.success(
                    f"Scanned **{result['sheets']}** sheet(s): "
                    f"**{result['inserted']}** inserted · "
                    f"**{result['updated']}** updated · "
                    f"**{result['skipped']}** skipped (blank colour)"
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Import failed: {exc}")

    st.divider()

    # Import / Export
    with st.expander("📤 Import / Export", expanded=(count == 0)):
        imp_col, exp_col, tpl_col = st.columns(3)

        # Template download
        tpl_col.download_button(
            "📋 Download template (.xlsx)",
            data=_ct_excel_template(),
            file_name="color_translation_template.xlsx",
            mime=XLSX_MIME,
            use_container_width=True,
            key="ct_tpl_dl",
        )

        # Export current data
        if count > 0:
            xl_buf = io.BytesIO()
            df_exp = store.to_dataframe()
            if "_id" in df_exp.columns:
                df_exp = df_exp.drop(columns=["_id"])
            with pd.ExcelWriter(xl_buf, engine="openpyxl") as w:
                df_exp.to_excel(w, sheet_name="Color Translations", index=False)
            exp_col.download_button(
                "⬇ Export all (.xlsx)",
                data=xl_buf.getvalue(),
                file_name="color_translations.xlsx",
                mime=XLSX_MIME,
                use_container_width=True,
                key="ct_exp_dl",
            )

        # Upload
        with imp_col:
            up_file = st.file_uploader(
                "Upload Excel (.xlsx)",
                type=["xlsx"],
                key="ct_ul",
                help="Must have columns: client, en_color, cn_color (optional: color_code, notes)",
            )
        if up_file is not None:
            replace_opt = st.selectbox(
                "On conflict:",
                ["Merge (upsert existing)", "Replace all data"],
                key="ct_ul_mode",
            )
            client_filter = ""
            if replace_opt == "Replace all data":
                st.warning("⚠️ This will delete ALL existing color translations before importing.")
                client_filter = "__ALL__"
            if st.button("▶ Run import", key="ct_ul_run"):
                try:
                    tmp = tempfile.mktemp(suffix=".xlsx")
                    with open(tmp, "wb") as fh:
                        fh.write(up_file.read())
                    if client_filter == "__ALL__":
                        with store._connect() as conn:
                            conn.execute("DELETE FROM color_translations")
                    result = store.import_from_xlsx(tmp)
                    st.success(
                        f"✅ Imported: **{result['inserted']}** new · "
                        f"**{result['updated']}** updated · "
                        f"**{result['skipped']}** skipped"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"Import failed: {exc}")

    st.divider()

    # View / Edit
    fc1, fc2, _, del_c = st.columns([2, 2, 2, 1])
    client_opts = ["All clients"] + clients
    sel_client = fc1.selectbox("Filter by client", client_opts, key="ct_client_filter")
    active_client = "" if sel_client == "All clients" else sel_client

    # Cascading brand filter
    brand_opts_raw = store.list_brands(active_client) if active_client else store.list_brands()
    brand_opts = ["All brands"] + brand_opts_raw
    sel_brand = fc2.selectbox("Filter by brand", brand_opts, key="ct_brand_filter")
    active_brand = "" if sel_brand == "All brands" else sel_brand

    df_view = store.to_dataframe(active_client, active_brand)
    if df_view.empty:
        display_df = pd.DataFrame(columns=_CT_DISPLAY_COLS)
        # Track an empty id-array so the save handler still works
        _ids_in_view: list = []
    else:
        # Add the Delete checkbox column (default False) and reorder to the
        # canonical display layout.
        df_view = df_view.copy()
        df_view["Delete"] = False
        display_df = df_view[_CT_DISPLAY_COLS]
        _ids_in_view = df_view["_id"].tolist() if "_id" in df_view.columns else []

    if df_view.empty:
        st.info("No color translations yet. Use the import section above or add rows in the editor below.")

    # Editable table
    edited = st.data_editor(
        display_df,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key="ct_editor",
        column_config=_CT_COL_CFG,
        height=420,
    )

    # Pair edited rows back with their DB ids by position (rows added in
    # the editor have no id and are inserted as new on save).
    def _ids_for_edited() -> list:
        n = min(len(edited), len(_ids_in_view))
        return list(_ids_in_view[:n])

    save_c, del_sel_c, del_filt_c, _ = st.columns([1, 1.2, 1.2, 3])

    if save_c.button("💾 Save changes", key="ct_save", use_container_width=True):
        if active_client:
            edited["Client"] = edited["Client"].replace("", active_client).fillna(active_client)
        if active_brand and "Brand" in edited.columns:
            edited["Brand"] = edited["Brand"].replace("", active_brand).fillna(active_brand)
        # Skip rows that have the Delete box ticked — the user can only
        # mean to remove them, not save them.
        save_df = edited[edited.get("Delete", False) != True] \
                  if "Delete" in edited.columns else edited
        saved = store.upsert_from_df(save_df)
        st.success(f"Saved {saved} row(s).")
        st.rerun()

    # ── Delete selected (checkbox-driven) ──────────────────────────────────
    selected_ids = []
    if "Delete" in edited.columns:
        ids_paired = _ids_for_edited()
        for i in range(min(len(edited), len(ids_paired))):
            if bool(edited.iloc[i].get("Delete")):
                selected_ids.append(int(ids_paired[i]))

    if del_sel_c.button(
        f"🗑 Delete selected ({len(selected_ids)})",
        key="ct_del_selected",
        use_container_width=True,
        disabled=(len(selected_ids) == 0),
        help="Delete the rows whose 🗑 checkbox is ticked.",
    ):
        n = store.delete_ids(selected_ids)
        st.success(f"Deleted {n} selected row(s).")
        st.rerun()

    # ── Delete filtered (legacy bulk-by-client/brand) ──────────────────────
    del_ctx = " / ".join(filter(None, [active_client, active_brand])) or None
    del_help = f"Delete all entries for: {del_ctx}" if del_ctx else "Select a client or brand to delete"
    if del_filt_c.button(
        "🗑 Delete filtered",
        key="ct_del_client",
        use_container_width=True,
        disabled=(not del_ctx),
        help=del_help,
    ):
        deleted = store.delete_by_client_brand(active_client, active_brand)
        st.success(f"Deleted {deleted} entries for '{del_ctx}'.")
        st.rerun()

    if count > 0:
        st.caption(
            f"Showing **{len(display_df):,}** of **{count:,}** entries. "
            "Filter by client and/or brand. Edit cells directly, then click Save."
        )

    # ── Audit log — every change made to the table is recorded here ────────
    st.divider()
    audit_count = store.audit_log_count()
    with st.expander(
        f"📜 Change history ({audit_count:,} entries)",
        expanded=False,
    ):
        st.caption(
            "Every insert / update / delete on the colour-translation table is "
            "recorded here.  Filter by client / brand / English colour, then "
            "the most recent changes (newest first) are shown.  Use this to "
            "see who changed what and when."
        )

        f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
        a_client = f1.selectbox(
            "Client", ["All clients"] + clients,
            key="ct_audit_client",
        )
        a_client_v = "" if a_client == "All clients" else a_client
        a_brand_opts = (store.list_brands(a_client_v) if a_client_v else
                        store.list_brands())
        a_brand = f2.selectbox(
            "Brand", ["All brands"] + a_brand_opts,
            key="ct_audit_brand",
        )
        a_brand_v = "" if a_brand == "All brands" else a_brand
        a_en = f3.text_input(
            "English colour",
            placeholder="(any)", key="ct_audit_en",
            help="Case-insensitive — \"navy\", \"NAVY\" both match.",
        )
        a_limit = f4.number_input(
            "Max rows", min_value=10, max_value=2000, value=200, step=10,
            key="ct_audit_limit",
        )

        log_rows = store.audit_log(
            limit=int(a_limit),
            client=a_client_v,
            brand=a_brand_v,
            en_color=a_en.strip() if a_en else "",
        )
        if log_rows:
            log_df = pd.DataFrame([{
                "When":      r["changed_at"][:19].replace("T", " "),
                "Who":       r["changed_by"],
                "Action":    r["action"],
                "Client":    r["client"],
                "Brand":     r["brand"],
                "EN":        r["en_color"],
                "Field":     r["field"],
                "Old":       r["old_value"] or "",
                "New":       r["new_value"] or "",
            } for r in log_rows])
            st.dataframe(
                log_df,
                width="stretch",
                hide_index=True,
                height=360,
                column_config={
                    "When":   st.column_config.TextColumn("When (UTC)", width="small"),
                    "Who":    st.column_config.TextColumn("Who",        width="small"),
                    "Action": st.column_config.TextColumn("Action",     width="small"),
                    "Field":  st.column_config.TextColumn("Field",      width="small"),
                    "Old":    st.column_config.TextColumn("Old value",  width="medium"),
                    "New":    st.column_config.TextColumn("New value",  width="medium"),
                },
            )
        else:
            st.info("No audit entries match the current filter.")

        if audit_count > 0:
            cclr1, _ = st.columns([1, 5])
            if cclr1.button(
                "🧹 Clear audit history",
                key="ct_audit_clear",
                help="Permanently delete all audit-log entries.  "
                     "Does NOT touch the colour-translation rows themselves.",
            ):
                # Two-step confirm via a session flag
                if st.session_state.get("_ct_audit_confirm"):
                    n = store.clear_audit_log()
                    st.session_state.pop("_ct_audit_confirm", None)
                    st.success(f"Cleared {n} audit entries.")
                    st.rerun()
                else:
                    st.session_state["_ct_audit_confirm"] = True
                    st.warning(
                        "This will erase the entire change history.  Click "
                        "the button again to confirm."
                    )
