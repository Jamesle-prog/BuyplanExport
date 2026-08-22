"""Color Name Translation tab — EN/CN lookup table by client and brand."""
from __future__ import annotations

import io
import os
import tempfile

import pandas as pd
import streamlit as st

from ui.i18n import t
from auth.companies import COMPANY_GIII, COMPANY_SKY_EAST
from ui.shared import XLSX_MIME, fragment_rerun
from ui.stores import get_color_translation_store

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_CT_COL_CFG = {
    "Delete":        st.column_config.CheckboxColumn(
        "🗑",
        width="small",
        help=t("Tick rows to delete, then click the **Delete selected** button "
             "below the table."),
        default=False,
    ),
    "Client":        st.column_config.TextColumn("Client", width="small"),
    "Brand":         st.column_config.TextColumn("Brand", width="small"),
    "English Color": st.column_config.TextColumn(
        "English Color",
        width="medium",
        help=t("Case-insensitive — \"NAVY\", \"navy\", \"Navy\" all collapse "
             "to the same row (stored as title case)."),
    ),
    "Chinese Color": st.column_config.TextColumn("Chinese Color (中文颜色)", width="medium"),
    "中文颜色代码":   st.column_config.TextColumn("中文颜色代码", width="small"),
    "Light/Dark":    st.column_config.SelectboxColumn(
        "Light/Dark (深浅)",
        width="small",
        options=["", "light", "dark"],
        help=t("Whether the body colour is light or dark.  Auto-derived from "
             "the English colour name when left blank — used to pick the "
             "main label colour (light body → 白色, dark body → 黑色)."),
    ),
    "Label Color":   st.column_config.SelectboxColumn(
        "Label Color (主标颜色)",
        width="small",
        options=["", "黑色", "白色"],
        help=t("Main label colour written into column I of the buyplan.  "
             "Auto-derived from Light/Dark when blank: "
             "light → 白色, dark → 黑色."),
    ),
    "Notes":         st.column_config.TextColumn("Notes", width="medium"),
}

_CT_DISPLAY_COLS = ["Delete", "Client", "Brand", "English Color", "Chinese Color",
                    "中文颜色代码", "Light/Dark", "Label Color", "Notes"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _ct_excel_template() -> bytes:
    """Return a blank Excel template for bulk color upload.

    Cached: the output is constant, so the workbook is built once per
    process instead of on every rerun of the tab.
    """
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


@st.cache_data(show_spinner=False)
def _ct_export_bytes(count: int, nonce: int) -> bytes:
    """Full-table Excel export for the download button.

    Cached so the whole-table query + workbook build only reruns when the
    data actually changes — keyed by the row *count* plus a session *nonce*
    that every save/delete/import handler bumps (via :func:`_bump_ct_nonce`),
    instead of rebuilding on every widget interaction in the tab.
    """
    df_exp = get_color_translation_store().to_dataframe()
    if "_id" in df_exp.columns:
        df_exp = df_exp.drop(columns=["_id"])
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df_exp.to_excel(w, sheet_name="Color Translations", index=False)
    return buf.getvalue()


def _bump_ct_nonce() -> None:
    """Invalidate the cached export after any data mutation."""
    st.session_state["_ct_data_nonce"] = st.session_state.get("_ct_data_nonce", 0) + 1


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_color_translation_tab() -> None:
    """Full Color Name Translation table — EN ↔ CN by client + brand."""
    store = get_color_translation_store()
    count = store.count()
    clients = store.list_clients()

    st.subheader(f"🎨 {t('Color Name Translation')}")
    st.caption(t(
        "Reference table mapping English color names to Chinese (中文颜色) by client and brand "
        "(e.g. GIII / Karl Lagerfeld, Sky East / Anna Field). "
        "Use the editor below to add/edit entries, or bulk-import from Excel."
    ))
    st.caption(t(
        "💡 This tab holds **colour translations** only. Fabric properties live in "
        "**🧵 Fabric DB**; style→fabric assignments and the 大货进度表 live in "
        "**📐 Reference Data**."
    ))

    # Stats bar + quick-load button
    brands_all = store.list_brands()
    m1, m2, m3, m4 = st.columns([1, 1, 1, 2])
    m1.metric(t("Total entries"), f"{count:,}")
    m2.metric(t("Clients"), f"{len(clients):,}")
    m3.metric(t("Brands"), f"{len(brands_all):,}")
    if m4.button(f"🔄 {t('Load colors from PO database')}",
                 help=f"{t('Scans all')} {COMPANY_GIII} {t('PO size rows and')} {COMPANY_SKY_EAST} "
                      + t("items for distinct "
                          "color names and adds any not already in this table. "
                          "Existing Chinese translations are preserved."),
                 use_container_width=True,
                 key="ct_load_from_db"):
        with st.spinner(f"{t('Scanning PO database for color names…')}"):
            result = store.load_from_po_data(skip_existing=True)
        ins = result["inserted"]
        skp = result["skipped"]
        src = result["sources"]
        if ins:
            st.success(
                f"{t('Added')} **{ins}** {t('new color(s) —')} "
                f"{src['giii']} {t('from')} {COMPANY_GIII} {t('POs,')} {src['sky_east']} {t('from')} {COMPANY_SKY_EAST}. "
                f"{skp} {t('already existed (preserved).')}"
            )
            _bump_ct_nonce()
            fragment_rerun()
        else:
            st.info(f"{t('No new colors found — all')} {skp} {t('color(s) were already in the table.')}")

    # ── Import from a 大货进度表 progress-tracker workbook ───────────────────
    with st.expander(f"📥 {t('Import from progress tracker (大货进度表)')}", expanded=False):
        st.caption(t(
            "Reads the **颜色 / 主标颜色 / 中文颜色** columns (and **BRAND** "
            "when present) from a 大货进度表 workbook and upserts every "
            "unique combination into this table.  English colour names are "
            "case-insensitive — \"NAVY\", \"navy\" and \"Navy\" all collapse "
            "into the same row stored as \"Navy\"."
        ))
        prog_file = st.file_uploader(
            t("Upload 大货进度表 workbook (.xlsx)"),
            type=["xlsx"],
            key="ct_progress_ul",
        )
        prog_client = st.selectbox(
            t("Assign rows to client"),
            [COMPANY_SKY_EAST, COMPANY_GIII],
            index=0,
            key="ct_progress_client",
            help=t("Which company should the imported rows be filed under?"),
        )
        if prog_file and st.button(f"▶ {t('Import progress tracker')}",
                                    key="ct_progress_run", use_container_width=True):
            tmp = tempfile.mktemp(suffix=".xlsx")
            try:
                with open(tmp, "wb") as fh:
                    fh.write(prog_file.read())
                with st.spinner(f"{t('Reading')} {prog_file.name}…"):
                    result = store.import_from_progress_xlsx(tmp, client=prog_client)
                st.success(
                    f"{t('Scanned')} **{result['sheets']}** {t('sheet(s):')} "
                    f"**{result['inserted']}** {t('inserted')} · "
                    f"**{result['updated']}** {t('updated')} · "
                    f"**{result['skipped']}** {t('skipped (blank colour)')}"
                )
                _bump_ct_nonce()
                fragment_rerun()
            except Exception as exc:
                st.error(f"{t('Import failed:')} {exc}")
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)

    st.divider()

    # Import / Export
    with st.expander(f"📤 {t('Import / Export')}", expanded=(count == 0)):
        imp_col, exp_col, tpl_col = st.columns(3)

        # Template download
        tpl_col.download_button(
            f"📋 {t('Download template (.xlsx)')}",
            data=_ct_excel_template(),
            file_name="color_translation_template.xlsx",
            mime=XLSX_MIME,
            use_container_width=True,
            key="ct_tpl_dl",
        )

        # Export current data
        if count > 0:
            exp_col.download_button(
                f"⬇ {t('Export all (.xlsx)')}",
                data=_ct_export_bytes(count, st.session_state.get("_ct_data_nonce", 0)),
                file_name="color_translations.xlsx",
                mime=XLSX_MIME,
                use_container_width=True,
                key="ct_exp_dl",
            )

        # Upload
        with imp_col:
            up_file = st.file_uploader(
                t("Upload Excel (.xlsx)"),
                type=["xlsx"],
                key="ct_ul",
                help=t("Must have columns: client, en_color, cn_color (optional: color_code, notes)"),
            )
        if up_file is not None:
            replace_opt = st.selectbox(
                t("On conflict:"),
                ["Merge (upsert existing)", "Replace all data"],
                format_func=lambda o: t(o),
                key="ct_ul_mode",
            )
            client_filter = ""
            if replace_opt == "Replace all data":
                st.warning(t("⚠️ This will delete ALL existing color translations before importing."))
                client_filter = "__ALL__"
            if st.button(f"▶ {t('Run import')}", key="ct_ul_run"):
                tmp = tempfile.mktemp(suffix=".xlsx")
                try:
                    with open(tmp, "wb") as fh:
                        fh.write(up_file.read())
                    if client_filter == "__ALL__":
                        with store._conn() as conn:
                            conn.execute("DELETE FROM color_translations")
                    result = store.import_from_xlsx(tmp)
                    st.success(
                        f"✅ {t('Imported:')} **{result['inserted']}** {t('new')} · "
                        f"**{result['updated']}** {t('updated')} · "
                        f"**{result['skipped']}** {t('skipped')}"
                    )
                    _bump_ct_nonce()
                    fragment_rerun()
                except Exception as exc:
                    st.error(f"{t('Import failed:')} {exc}")
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)

    st.divider()

    # View / Edit
    fc1, fc2, _, del_c = st.columns([2, 2, 2, 1])
    client_opts = ["All clients"] + clients
    sel_client = fc1.selectbox(t("Filter by client"), client_opts,
                               format_func=lambda o: t(o) if o == "All clients" else o,
                               key="ct_client_filter")
    active_client = "" if sel_client == "All clients" else sel_client

    # Cascading brand filter (reuse the unfiltered list fetched for the stats bar)
    brand_opts_raw = store.list_brands(active_client) if active_client else brands_all
    brand_opts = ["All brands"] + brand_opts_raw
    sel_brand = fc2.selectbox(t("Filter by brand"), brand_opts,
                              format_func=lambda o: t(o) if o == "All brands" else o,
                              key="ct_brand_filter")
    active_brand = "" if sel_brand == "All brands" else sel_brand

    df_view = store.to_dataframe(active_client, active_brand)
    if df_view.empty:
        display_df = pd.DataFrame(columns=["_id"] + _CT_DISPLAY_COLS)
    else:
        # Add the Delete checkbox column (default False) and reorder to the
        # canonical display layout.
        df_view = df_view.copy()
        # Compat: older cached store versions return "Color Code"; rename on the fly.
        if "Color Code" in df_view.columns and "中文颜色代码" not in df_view.columns:
            df_view = df_view.rename(columns={"Color Code": "中文颜色代码"})
        df_view["Delete"] = False
        # "_id" rides along hidden (column_config None) so each edited row
        # stays paired with its DB id.  The old positional pairing
        # (_ids_in_view[:n]) deleted the WRONG row as soon as the user
        # removed a row inline in this dynamic editor.
        display_df = df_view[["_id"] + _CT_DISPLAY_COLS]

    if df_view.empty:
        st.info(t("No color translations yet. Use the import section above or add rows in the editor below."))

    # Editable table
    edited = st.data_editor(
        display_df,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key="ct_editor",
        column_config={**_CT_COL_CFG, "_id": None},
        height=420,
    )

    save_c, del_sel_c, del_filt_c, _ = st.columns([1, 1.2, 1.2, 3])

    if save_c.button(f"💾 {t('Save changes')}", key="ct_save", use_container_width=True):
        if active_client:
            edited["Client"] = edited["Client"].replace("", active_client).fillna(active_client)
        if active_brand and "Brand" in edited.columns:
            edited["Brand"] = edited["Brand"].replace("", active_brand).fillna(active_brand)
        # Skip rows that have the Delete box ticked — the user can only
        # mean to remove them, not save them.
        save_df = edited[edited.get("Delete", False) != True] \
                  if "Delete" in edited.columns else edited
        # The hidden _id pairing column is not part of the store schema.
        if "_id" in save_df.columns:
            save_df = save_df.drop(columns=["_id"])
        saved = store.upsert_from_df(save_df)
        st.success(f"{t('Saved')} {saved} {t('row(s).')}")
        _bump_ct_nonce()
        fragment_rerun()

    # ── Delete selected (checkbox-driven) ──────────────────────────────────
    # Ids come from the row's own hidden _id — immune to inline row
    # removal shifting positions.  Rows added in the editor have no _id
    # (NaN) and are skipped: they're not in the DB yet.
    selected_ids = []
    if "Delete" in edited.columns and "_id" in edited.columns:
        for _, _row in edited[edited["Delete"] == True].iterrows():
            if pd.notna(_row["_id"]):
                selected_ids.append(int(_row["_id"]))

    if del_sel_c.button(
        f"🗑 {t('Delete selected')} ({len(selected_ids)})",
        key="ct_del_selected",
        use_container_width=True,
        disabled=(len(selected_ids) == 0),
        help=t("Delete the rows whose 🗑 checkbox is ticked."),
    ):
        n = store.delete_ids(selected_ids)
        st.success(f"{t('Deleted')} {n} {t('selected row(s).')}")
        _bump_ct_nonce()
        fragment_rerun()

    # ── Delete filtered (legacy bulk-by-client/brand) ──────────────────────
    del_ctx = " / ".join(filter(None, [active_client, active_brand])) or None
    del_help = f"{t('Delete all entries for:')} {del_ctx}" if del_ctx else t("Select a client or brand to delete")
    if del_filt_c.button(
        f"🗑 {t('Delete filtered')}",
        key="ct_del_client",
        use_container_width=True,
        disabled=(not del_ctx),
        help=del_help,
    ):
        deleted = store.delete_by_client_brand(active_client, active_brand)
        st.success(f"{t('Deleted')} {deleted} {t('entries for')} '{del_ctx}'.")
        _bump_ct_nonce()
        fragment_rerun()

    if count > 0:
        st.caption(
            f"{t('Showing')} **{len(display_df):,}** {t('of')} **{count:,}** {t('entries.')} "
            + t("Filter by client and/or brand. Edit cells directly, then click Save.")
        )

    # ── Audit log — every change made to the table is recorded here ────────
    st.divider()
    audit_count = store.audit_log_count()
    with st.expander(
        f"📜 {t('Change history')} ({audit_count:,} {t('entries')})",
        expanded=False,
    ):
        st.caption(t(
            "Every insert / update / delete on the colour-translation table is "
            "recorded here.  Filter by client / brand / English colour, then "
            "the most recent changes (newest first) are shown.  Use this to "
            "see who changed what and when."
        ))

        f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
        a_client = f1.selectbox(
            t("Client"), ["All clients"] + clients,
            format_func=lambda o: t(o) if o == "All clients" else o,
            key="ct_audit_client",
        )
        a_client_v = "" if a_client == "All clients" else a_client
        a_brand_opts = (store.list_brands(a_client_v) if a_client_v else
                        brands_all)
        a_brand = f2.selectbox(
            t("Brand"), ["All brands"] + a_brand_opts,
            format_func=lambda o: t(o) if o == "All brands" else o,
            key="ct_audit_brand",
        )
        a_brand_v = "" if a_brand == "All brands" else a_brand
        a_en = f3.text_input(
            t("English colour"),
            placeholder=t("(any)"), key="ct_audit_en",
            help=t("Case-insensitive — \"navy\", \"NAVY\" both match."),
        )
        a_limit = f4.number_input(
            t("Max rows"), min_value=10, max_value=2000, value=200, step=10,
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
                    "When":   st.column_config.TextColumn(t("When (UTC)"), width="small"),
                    "Who":    st.column_config.TextColumn(t("Who"),        width="small"),
                    "Action": st.column_config.TextColumn(t("Action"),     width="small"),
                    "Field":  st.column_config.TextColumn(t("Field"),      width="small"),
                    "Old":    st.column_config.TextColumn(t("Old value"),  width="medium"),
                    "New":    st.column_config.TextColumn(t("New value"),  width="medium"),
                },
            )
        else:
            st.info(t("No audit entries match the current filter."))

        if audit_count > 0:
            # Two-step confirm: while armed, the warning stays visible across
            # reruns and the button itself says what a second click will do —
            # the old transient warning was easy to miss, and the armed flag
            # silently persisted so a much later click deleted immediately.
            _armed = st.session_state.get("_ct_audit_confirm", False)
            if _armed:
                st.warning(
                    f"⚠️ {t('This will erase the entire change history')} "
                    f"({audit_count:,} {t('entries')}). "
                    + t("Click **Confirm clear** to proceed, or Cancel to keep it.")
                )
            cclr1, cclr2, _ = st.columns([1.6, 1, 3.4])
            _clr_label = (f"🧹 {t('Confirm clear')} ({audit_count:,} {t('entries')})"
                          if _armed else f"🧹 {t('Clear audit history')}")
            if cclr1.button(
                _clr_label,
                key="ct_audit_clear",
                type="primary" if _armed else "secondary",
                help=t("Permanently delete all audit-log entries.  "
                       "Does NOT touch the colour-translation rows themselves."),
            ):
                if _armed:
                    n = store.clear_audit_log()
                    st.session_state.pop("_ct_audit_confirm", None)
                    st.success(f"{t('Cleared')} {n} {t('audit entries.')}")
                    fragment_rerun()
                else:
                    st.session_state["_ct_audit_confirm"] = True
                    fragment_rerun()
            if _armed and cclr2.button(t("Cancel"), key="ct_audit_clear_cancel"):
                st.session_state.pop("_ct_audit_confirm", None)
                fragment_rerun()
