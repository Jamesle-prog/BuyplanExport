"""Admin panel: Application-wide settings."""
from __future__ import annotations

import streamlit as st

from ui.session_keys import SK, COLOR_SOURCE_DB, COLOR_SOURCE_PROGRESS
from ui.stores import get_app_settings_store

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SETTING_COLOR_SOURCE = "default_color_source"

_COLOR_SOURCE_OPTIONS: dict[str, str] = {
    COLOR_SOURCE_DB:       "🗄 Internal Database (Colors tab)",
    COLOR_SOURCE_PROGRESS: "📂 大货进度表 (HHN Contract No. file)",
}

_COLOR_SOURCE_HELP: dict[str, str] = {
    COLOR_SOURCE_DB: (
        "Look up 中文颜色 / 中文颜色代码 from the **Colors** tab "
        "(color_translation table).  "
        "Keys: Client · Brand · English color name."
    ),
    COLOR_SOURCE_PROGRESS: (
        "Look up 中文颜色 / 中文颜色代码 from the uploaded **大货进度表** "
        "(HHN Contract No. file).  "
        "Keys: PC No · 款式 · 颜色 (with fallback tiers)."
    ),
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_settings_admin() -> None:
    st.markdown("### ⚙️ Application Settings")
    st.caption(
        "Settings here apply to all users.  "
        "Individual users can still override per-session where allowed."
    )

    store = get_app_settings_store()

    # ── Chinese color mapping default source ────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🎨 Chinese Color Mapping — Default Source")
    st.caption(
        "Controls the pre-selected option for the **Chinese color mapping source** "
        "radio on the Sky East tab.  New sessions start with this value; "
        "users can still change it within their session."
    )

    current = store.get(_SETTING_COLOR_SOURCE, COLOR_SOURCE_DB)
    options  = list(_COLOR_SOURCE_OPTIONS.keys())
    labels   = list(_COLOR_SOURCE_OPTIONS.values())
    idx      = options.index(current) if current in options else 0

    chosen_label = st.radio(
        "Default source",
        labels,
        index=idx,
        key="admin_default_color_src_radio",
    )
    chosen_key = options[labels.index(chosen_label)]
    st.info(_COLOR_SOURCE_HELP[chosen_key], icon="ℹ️")

    if st.button("💾 Save", key="admin_settings_save", type="primary"):
        store.set(
            _SETTING_COLOR_SOURCE,
            chosen_key,
            updated_by=st.session_state.get(SK.USERNAME, ""),
        )
        st.success(
            f"✅ Default color source saved: **{_COLOR_SOURCE_OPTIONS[chosen_key]}**  \n"
            "New sessions will start with this selection."
        )
