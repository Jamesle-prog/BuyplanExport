"""Admin panel: Application-wide settings."""
from __future__ import annotations

import os

import streamlit as st

from ui.session_keys import SK, COLOR_SOURCE_DB, COLOR_SOURCE_PROGRESS
from ui.stores import get_app_settings_store
from po_extractor.store.app_settings_store import KEY_DEFAULT_COLOR_SOURCE

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SETTING_COLOR_SOURCE = KEY_DEFAULT_COLOR_SOURCE

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

    # ── Fabric Master Database ───────────────────────────────────────────────
    st.markdown("---")
    _show_fabric_db_settings()


# ---------------------------------------------------------------------------
# Fabric Master DB sub-section
# ---------------------------------------------------------------------------

def _show_fabric_db_settings() -> None:
    from po_extractor.config import (
        get_fabric_db_path, save_fabric_db_path, DB_PATH,
    )
    from po_extractor.store.fabric_master_store import FabricMasterStore
    from fabric_master_client import FabricMasterClient

    st.markdown("#### 🗄 Fabric Master Database")
    st.caption(
        "The fabric master lives in its **own dedicated SQLite file** so that "
        "other applications can share the same data.  Point any app's "
        "`FabricMasterStore` (or copy `fabric_master_client.py`) at the path "
        "below to get read access."
    )

    current_path = get_fabric_db_path()

    # ── Current status ───────────────────────────────────────────────────────
    ok, status_msg = FabricMasterClient.test_connection(current_path)
    if ok:
        st.success(f"✅ Connected — {status_msg}  \n`{current_path}`")
    else:
        st.warning(f"⚠️ Cannot connect: {status_msg}  \n`{current_path}`")

    env_override = os.environ.get("FABRIC_DB_PATH", "").strip()
    if env_override:
        st.info(
            f"ℹ️ Path is overridden by the `FABRIC_DB_PATH` environment variable.  "
            f"Clear the env var to use the path configured below.",
            icon="🔒",
        )

    # ── Path editor ──────────────────────────────────────────────────────────
    with st.expander("✏️ Change fabric master DB path", expanded=not ok):
        st.caption(
            "Enter an absolute path to the `fabric_master.db` file.  "
            "All apps sharing this file must have read access to the same location "
            "(e.g. a mapped network drive or shared folder)."
        )
        new_path = st.text_input(
            "Fabric master DB path",
            value=current_path,
            key="admin_fabric_db_path_input",
            placeholder=r"C:\Shared\fabric_master.db",
            disabled=bool(env_override),
        )

        col_test, col_save = st.columns([1, 1])
        with col_test:
            if st.button("🔌 Test connection", key="admin_fabric_test_btn"):
                test_ok, test_msg = FabricMasterClient.test_connection(new_path)
                if test_ok:
                    st.success(f"✅ {test_msg}")
                else:
                    st.error(f"❌ {test_msg}")

        with col_save:
            if st.button(
                "💾 Save path",
                key="admin_fabric_save_path_btn",
                type="primary",
                disabled=bool(env_override),
            ):
                save_fabric_db_path(new_path.strip())
                st.success("✅ Path saved to `fabric_config.json`.  Reload the page to apply.")
                st.rerun()

    # ── Migration ────────────────────────────────────────────────────────────
    with st.expander("📦 Migrate existing fabric data from main app DB"):
        st.caption(
            "If you previously used this app before the centralised fabric DB "
            "was introduced, your fabric data is still in `po_history.db`.  "
            "Click below to copy it into the dedicated `fabric_master.db`."
        )

        src_count = _count_fabric_in_db(DB_PATH)
        dst_count = FabricMasterStore(current_path).count() if ok else 0

        col1, col2 = st.columns(2)
        col1.metric("Records in po_history.db", src_count)
        col2.metric("Records in fabric_master.db", dst_count)

        if src_count == 0:
            st.info("No fabric records found in `po_history.db` — nothing to migrate.")
        else:
            if st.button(
                f"📦 Migrate {src_count} records → fabric_master.db",
                key="admin_fabric_migrate_btn",
                type="primary",
            ):
                with st.spinner("Migrating…"):
                    result = FabricMasterStore.migrate_from_db(DB_PATH, current_path)
                st.success(
                    f"✅ Migration complete.  {result['message']}  \n"
                    f"fabric_master.db now has **{FabricMasterStore(current_path).count()}** records."
                )

    # ── Integration guide ────────────────────────────────────────────────────
    with st.expander("📋 How other apps connect to this database"):
        st.markdown(
            "**Option A — Copy `fabric_master_client.py` (no dependencies)**\n\n"
            "Drop `fabric_master_client.py` (found in the PO_Automation_GIII "
            "project root) into the other app.  Standard library only.\n\n"
            "```python\n"
            "from fabric_master_client import FabricMasterClient\n\n"
            f'client = FabricMasterClient(r"{current_path}")\n'
            "record = client.get_by_quality_no('FM-0001')\n"
            "batch  = client.get_batch_enrichment(['FM-0001', 'FM-0002'])\n"
            "```\n\n"
            "**Option B — Use `FabricMasterStore` directly (if po_extractor is on sys.path)**\n\n"
            "```python\n"
            "from po_extractor.store.fabric_master_store import FabricMasterStore\n\n"
            f'store = FabricMasterStore(r"{current_path}")\n'
            "record = store.get_by_quality_no('FM-0001')\n"
            "```\n\n"
            "**Option C — Environment variable**\n\n"
            "Set `FABRIC_DB_PATH` in the other app's environment:\n"
            "```\n"
            f"FABRIC_DB_PATH={current_path}\n"
            "```\n"
            "Then `from po_extractor.store import get_fabric_master_store` "
            "will automatically point to the shared file."
        )


# _count_fabric_in_db replaced by po_extractor.store.count_fabric_rows
from po_extractor.store import count_fabric_rows as _count_fabric_in_db  # noqa: E402
