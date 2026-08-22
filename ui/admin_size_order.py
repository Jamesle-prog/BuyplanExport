"""Admin: Size Order management view."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.i18n import t
from po_extractor.utils.size_config import get_size_order, save_size_order


def show_size_order_admin() -> None:
    """Admin UI: manage the ordered size list used in all Excel exports."""
    st.subheader(f"📐 {t('Size Order')}")
    st.caption(t(
        "Controls the column order of sizes in buy-plan, color-plan, PO-summary, and "
        "cross-check exports. Sizes not in this list are appended at the end in the "
        "order they appear in the data. Changes take effect on the next export."
    ))

    current = get_size_order()

    df_sizes = pd.DataFrame({"Size": current})
    st.markdown(f"**{t('Current size order')}** — {t('edit, reorder rows, or add new sizes below:')}")
    edited = st.data_editor(
        df_sizes,
        num_rows="dynamic",
        width="content",
        hide_index=False,
        key="admin_size_editor",
        column_config={"Size": st.column_config.TextColumn(t("Size code"), width="small")},
        height=min(600, max(200, len(current) * 35 + 40)),
    )
    st.caption(t(
        "ℹ️ Drag rows to reorder. The row index shown is the column position (0-based). "
        "Delete a row to remove a size from the known order (it will still appear in "
        "exports, just after all known sizes)."
    ))

    c1, c2 = st.columns([1, 3])
    if c1.button(f"💾 {t('Save size order')}", key="admin_size_save", width="stretch"):
        # pd.notna first: a blank new row arrives as None/NaN, and
        # str(None)=="None"/str(nan)=="nan" would otherwise survive the strip
        # check and get saved as bogus size codes "NONE"/"NAN".
        new_sizes = [
            str(v).strip().upper()
            for v in edited["Size"]
            if pd.notna(v) and str(v).strip()
        ]
        if not new_sizes:
            st.error(t("Size list cannot be empty."))
        else:
            save_size_order(new_sizes)
            st.success(f"{t('Saved')} {len(new_sizes)} {t('sizes.')}")
            st.rerun()

    if c2.button(f"↩️ {t('Reset to defaults')}", key="admin_size_reset",
                 width="content"):
        from po_extractor.config import SIZE_ORDER as _DEFAULT_SIZE_ORDER
        save_size_order(list(_DEFAULT_SIZE_ORDER))
        st.success(t("Reset to built-in defaults."))
        st.rerun()
