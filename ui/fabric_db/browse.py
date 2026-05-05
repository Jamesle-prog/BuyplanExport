"""Browse and detail-view helpers for the Fabric DB tab."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.fabric_db._shared import (
    FABRIC_DB_LIST_RENAME,
    FABRIC_DB_DETAIL_RENAME,
    FABRIC_DB_PAGE_SIZE,
    _fabric_db_list_table,
)


def _fabric_db_paginated_list(store, total_count: int) -> None:
    """Full paginated browser (all records; used when no search query is active)."""
    page_size = FABRIC_DB_PAGE_SIZE
    n_pages   = max(1, (total_count + page_size - 1) // page_size)

    # Clamp stored page in case data shrank between reruns
    cur = int(st.session_state.get("fabric_db_page", 1) or 1)
    cur = max(1, min(cur, n_pages))

    nav_l, nav_mid, nav_r = st.columns([1, 2, 1])
    with nav_l:
        st.button("◀ Prev", disabled=(cur <= 1), key="fabric_db_prev",
                  on_click=lambda: st.session_state.update(
                      {"fabric_db_page": max(1, cur - 1)}))
    with nav_mid:
        picked = st.number_input(
            f"Page (1 – {n_pages})",
            min_value=1, max_value=n_pages, value=cur, step=1,
            key="fabric_db_page_input",
        )
        if picked != cur:
            st.session_state["fabric_db_page"] = int(picked)
            cur = int(picked)
    with nav_r:
        st.button("Next ▶", disabled=(cur >= n_pages), key="fabric_db_next",
                  on_click=lambda: st.session_state.update(
                      {"fabric_db_page": min(n_pages, cur + 1)}))

    offset = (cur - 1) * page_size
    rows   = store.list_page(offset=offset, limit=page_size)
    _fabric_db_list_table(pd.DataFrame(rows))

    start = offset + 1 if rows else 0
    end   = offset + len(rows)
    st.caption(
        f"Showing **{start:,} – {end:,}** of **{total_count:,}** fabric(s) "
        f"· page **{cur} / {n_pages}**"
    )


def _fabric_db_detail_card(store) -> None:
    """Render the 'view full detail for a specific fabric' expander."""
    with st.expander("🔎 View full detail for a specific fabric"):
        qno = st.text_input(
            "Enter 公司面料编号 exactly",
            placeholder="e.g. MQ-BD181446",
            key="fabric_db_detail_input",
        )
        if not qno.strip():
            return
        rec = store.get_by_quality_no(qno.strip())
        if not rec:
            st.warning(f"No fabric found with Quality No. '{qno.strip()}'")
            return

        # Key info — two rows of 3 metrics
        ki = st.columns(3)
        ki[0].metric("面料成分（英文）", rec.get("composition_en") or "—")
        ki[1].metric("克重 GSM",
                     f"{int(rec['weight_gsm'])}" if rec.get("weight_gsm") else "—")
        ki[2].metric("有效门幅 CM",
                     f"{int(rec['cuttable_width_cm'])}" if rec.get("cuttable_width_cm") else "—")

        ki2 = st.columns(3)
        ki2[0].metric("烫缩率",
                      f"{rec['shrinkage_rate']:.2f}" if rec.get("shrinkage_rate") is not None else "—")
        ki2[1].metric("短码率",
                      f"{rec['short_rate']:.2f}" if rec.get("short_rate") is not None else "—")
        ki2[2].metric("备注说明", rec.get("notes_cn") or "—")

        st.markdown(f"**综合标识 Key:** `{rec.get('display_key', '')}`")
        st.divider()

        detail_df = pd.DataFrame([
            {"字段": FABRIC_DB_DETAIL_RENAME.get(k, k), "值": str(v) if v is not None else ""}
            for k, v in rec.items()
        ])
        st.dataframe(detail_df, width="stretch", hide_index=True)
