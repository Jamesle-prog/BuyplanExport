"""Fabric Master Database tab — shell entry point.

Implementation is split across the ui/fabric_db/ sub-package:
  _shared.py        — constants and low-level display helpers
  import_section.py — import, update, and delete fabric records
  browse.py         — paginated browser and detail card
  validation.py     — composition and field validation + cross-system checks
  fiber_manager.py  — known-fiber dictionary management
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.fabric_db._shared import _fabric_db_stats_bar, _fabric_db_list_table
from ui.fabric_db.import_section import (
    _fabric_db_upload_section,
    _fabric_db_delete_section,
)
from ui.fabric_db.browse import _fabric_db_paginated_list, _fabric_db_detail_card
from ui.fabric_db.validation import (
    _fabric_db_validation_section,
    _fabric_db_cross_system_section,
)
from ui.fabric_db.fiber_manager import _fabric_db_fiber_manager
from ui.stores import get_fabric_master_store


def show_fabric_db_tab() -> None:
    """Browse and update the fabric master database (面料统计表)."""
    store = get_fabric_master_store()
    count = store.count()
    last  = store.last_import_info()

    st.subheader("🧵 Fabric Master Database")
    st.caption(
        "Fabric reference data from **面料统计表.xlsx**. "
        "Upload a new version of the file below to refresh all records. "
        "Use the search box to look up any fabric by code, composition, or supplier."
    )

    _fabric_db_stats_bar(count, last)
    st.divider()
    _fabric_db_upload_section(store, count)
    _fabric_db_delete_section(store)
    st.divider()

    if count == 0:
        st.info("No fabric data yet. Upload a 面料统计表.xlsx file above to get started.")
        return

    search_q = st.text_input(
        "🔍 Search by Quality No., composition, supplier, or fabric structure",
        placeholder="e.g. MQ-BD181446 · French Terry · 贝德 · Cotton",
        key="fabric_db_search",
    )

    if search_q.strip():
        # Search mode — flat list, up to 300 matches
        rows = store.search(search_q.strip(), limit=300)
        if not rows:
            st.warning("No fabrics match your search.")
            return
        _fabric_db_list_table(pd.DataFrame(rows))
        st.caption(f"{len(rows):,} match(es) shown (search limit: 300)")
    else:
        # Browse mode — paginated through all records
        _fabric_db_paginated_list(store, count)

    st.divider()
    _fabric_db_validation_section(store)
    st.divider()
    _fabric_db_cross_system_section(store)
    st.divider()
    _fabric_db_fiber_manager()
    st.divider()
    _fabric_db_detail_card(store)
