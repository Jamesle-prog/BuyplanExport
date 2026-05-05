"""Import, add, update, and delete fabric records."""
from __future__ import annotations

import os
import string
import tempfile
import time

import pandas as pd
import streamlit as st

from ui.fabric_db._shared import FABRIC_DB_LIST_RENAME


def _fabric_db_do_import(store, uploaded) -> None:
    """Write *uploaded* to a temp file, call import_from_xlsx, show result."""
    with st.spinner("Importing fabric data…"):
        try:
            t0 = time.time()
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = tmp.name
            result = store.import_from_xlsx(tmp_path, source_file_name=uploaded.name)
            os.unlink(tmp_path)
            m, s = divmod(int(time.time() - t0), 60)
            st.success(
                f"✅ Import complete in {m}:{s:02d} — "
                f"**{result['inserted']}** new, "
                f"**{result['updated']}** updated, "
                f"**{result['skipped']}** skipped "
                f"(total: {result['total']} fabrics)"
            )
            # Show detected column map so user can verify header detection
            col_map = result.get("col_map", {})
            unmatched = result.get("unmatched_headers", [])
            if col_map:
                with st.expander("🗂 Detected column layout", expanded=False):
                    def _col_letter(n):
                        letters = ""
                        while n:
                            n, r = divmod(n - 1, 26)
                            letters = string.ascii_uppercase[r] + letters
                        return letters
                    rows = [
                        {"Column": _col_letter(c), "Field": f}
                        for f, c in sorted(col_map.items(), key=lambda x: x[1])
                    ]
                    st.dataframe(pd.DataFrame(rows), hide_index=True,
                                 use_container_width=False)
                    if unmatched:
                        st.caption(
                            "⚠️ Unrecognised headers (not mapped to any field): "
                            + ", ".join(f"Col {_col_letter(c)} '{h}'"
                                        for c, h in unmatched[:10])
                        )
            st.rerun()
        except Exception as exc:
            st.error(f"Import failed: {exc}")


def _fabric_db_upload_section(store, count: int) -> None:
    """Single expander with radio-button toggle: Update/Add  vs  Clear All & Reimport."""
    with st.expander("📂 Import Fabric Table (面料统计表.xlsx)",
                     expanded=(count == 0)):

        mode = st.radio(
            "Import mode",
            ["➕ Update / Add", "🗑 Clear All & Reimport"],
            horizontal=True,
            key="fabric_db_import_mode",
            label_visibility="collapsed",
        )

        if mode == "➕ Update / Add":
            st.caption(
                "Existing records with the same 公司面料编号 will be updated; "
                "new records will be added.  No data is deleted."
            )
            uploaded = st.file_uploader(
                "面料统计表.xlsx",
                type=["xlsx", "xlsm", "xls"],
                key="fabric_db_uploader",
                label_visibility="collapsed",
            )
            if uploaded and st.button("▶  Import Fabric Data", type="primary",
                                       key="fabric_db_import"):
                _fabric_db_do_import(store, uploaded)

        else:  # Clear All & Reimport
            st.warning(
                "**Every existing record will be deleted** before importing the new file. "
                "Use this when the column layout has changed or you need a clean slate. "
                "This action cannot be undone."
            )
            reimport_file = st.file_uploader(
                "面料统计表.xlsx (full replacement)",
                type=["xlsx", "xlsm", "xls"],
                key="fabric_db_reimport_uploader",
                label_visibility="collapsed",
            )
            confirmed = st.checkbox(
                "I understand all existing fabric records will be permanently deleted",
                key="fabric_db_clear_confirm",
            )
            if reimport_file and confirmed:
                if st.button("🗑  Delete All & Reimport", type="primary",
                             key="fabric_db_clear_reimport"):
                    deleted = store.delete_all()
                    st.info(f"🗑 {deleted:,} record(s) deleted.")
                    _fabric_db_do_import(store, reimport_file)
            elif reimport_file and not confirmed:
                st.caption("☝️ Tick the checkbox above to enable the button.")


def _fabric_db_delete_section(store) -> None:
    """Expander: search and delete individual fabric records by 公司面料编号."""
    with st.expander("🗑 Delete Selected Records", expanded=False):
        st.caption(
            "Search for fabrics to delete.  Select one or more rows, then confirm deletion."
        )

        del_q = st.text_input(
            "Search by 公司面料编号, composition, or supplier",
            placeholder="e.g. BO-DW240485 · Cotton · 德帽",
            key="fabric_db_del_search",
        )

        if not del_q.strip():
            st.info("Enter a search term above to find records.")
            return

        rows = store.search(del_q.strip(), limit=200)
        if not rows:
            st.warning("No records match your search.")
            return

        df = pd.DataFrame(rows)
        show_cols = [c for c in FABRIC_DB_LIST_RENAME if c in df.columns]
        display_df = df[show_cols].rename(columns=FABRIC_DB_LIST_RENAME)

        # Let the user pick rows via multiselect on quality_no
        all_qnos = df["quality_no"].tolist()
        selected = st.multiselect(
            f"Select record(s) to delete ({len(all_qnos)} found):",
            options=all_qnos,
            key="fabric_db_del_sel",
        )

        # Show the full table for reference
        st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            column_config={
                "综合标识 Key": st.column_config.TextColumn(width="large"),
                "克重 GSM":    st.column_config.NumberColumn(format="%.0f"),
                "有效门幅 CM": st.column_config.NumberColumn(format="%.0f"),
                "烫缩率":      st.column_config.NumberColumn(format="%.2f"),
                "短码率":      st.column_config.NumberColumn(format="%.2f"),
            },
        )

        if not selected:
            return

        st.warning(f"**{len(selected)}** record(s) selected for deletion: "
                   + ", ".join(f"`{q}`" for q in selected[:10])
                   + (" …" if len(selected) > 10 else ""))

        if st.button(f"🗑  Delete {len(selected)} record(s)", type="primary",
                     key="fabric_db_del_confirm"):
            deleted = store.delete_by_quality_nos(selected)
            st.success(f"✅ {deleted} record(s) deleted.")
            # Clear selection and rerun
            st.session_state.pop("fabric_db_del_sel", None)
            st.rerun()
