"""PO Extractor — Streamlit UI."""
import os
import sys

import streamlit as st

APP_VERSION = "1.8.4"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth.license import validate_license
from auth.companies import ensure_defaults_seeded
from auth.users import (
    change_password, get_user_companies, is_admin,
    user_exists, verify_password,
)
from po_extractor.ui_helpers import load_live_schema as _load_live_schema_impl
from po_extractor.config import SCHEMA_PATH as _SCHEMA_PATH_CFG, CACHE_TTL_SECONDS
from ui.session_keys import SK

# Seed default companies on startup (idempotent)
ensure_defaults_seeded()

_SCHEMA_PATH = _SCHEMA_PATH_CFG


# ── Live output schema (editable via Admin UI) ────────────────────────────────

# Live schema helpers — implementation in po_extractor.ui_helpers.schema
def _load_live_schema() -> list[dict]:
    return _load_live_schema_impl(_SCHEMA_PATH)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def _cached_schema() -> list[dict]:
    """Cached live schema — refreshes every 60 s or when cleared explicitly."""
    return _load_live_schema()


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"PO Extractor v{APP_VERSION}",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Login card */
.login-card {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 12px;
    padding: 2.5rem 2rem;
}
/* Subtle file uploader border */
[data-testid="stFileUploader"] {
    border: 2px dashed #ced4da;
    border-radius: 8px;
    padding: 0.5rem;
}
/* Status badges used in processing logs */
.badge-ok  { color: #198754; font-weight: 600; }
.badge-err { color: #dc3545; font-weight: 600; }
/* Metric label smaller on stat rows */
[data-testid="stMetricLabel"] { font-size: 0.8rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
for key, default in [
    (SK.LOGGED_IN,        False),
    (SK.USERNAME,         None),
    (SK.RESULTS,          None),
    (SK.HISTORY_RESULTS,  None),
    (SK.HISTORY_BP_BYTES, None),   # buy-plan-only bytes (GIII history)
    (SK.SE_BP_BYTES,      None),   # buy-plan bytes (Sky East history)
    (SK.SE_BP_NAME,       None),   # buy-plan filename (Sky East history)
    (SK.SE_NK_BYTES,      None),   # 核料 zip bytes (Sky East history)
    (SK.SE_NK_COUNT,      0),      # number of 核料 workbooks in the zip
    (SK.SE_NK_REASON,     None),   # reason string when 核料 generation returned nothing
    (SK.SE_BP_CMP,        None),   # cross-comparison DataFrame
    (SK.SHOW_CHANGE_PW,   False),
    (SK.SHOW_ADMIN,       False),
    (SK.PARSE_LOG,        []),
    # Sky East tab
    (SK.SE_RESULTS,      None),    # list of save result dicts
    (SK.SE_LOG,          []),      # processing log lines
    (SK.SE_CONTRACTS,    None),    # list of SkyEastContract parsed
    (SK.SE_IMAGE_CACHE,  {}),      # image_id → bytes
    (SK.SE_DL_BYTES,     None),    # generated download bytes
    (SK.SE_DL_FNAME,     None),    # generated download filename
    (SK.SE_DL_MIME,      None),    # generated download MIME type
    (SK.SE_WL_BYTES,     None),    # wash label download bytes
    (SK.SE_WL_FNAME,     None),    # wash label download filename
    (SK.SE_WL_PENDING,   None),    # pending validation context
    # UI language
    (SK.UI_LANG,         "en"),    # "en" | "zh"
    # GIII reference data panel
    (SK.GIII_MAPPING,    None),    # result of last mapping import
    # Sky East — color mapping source (None = resolve from admin default on first render)
    (SK.SE_COLOR_SOURCE, None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# i18n — bilingual column header support
# ---------------------------------------------------------------------------

# English label → Chinese label mapping for all table headers
# License check (runs before anything else)
# ---------------------------------------------------------------------------
license_ok, license_msg = validate_license()
if not license_ok:
    st.error(f"⛔ License error: {license_msg}")
    st.stop()

# ---------------------------------------------------------------------------
# Guard: no users yet → show setup prompt
# ---------------------------------------------------------------------------
if not user_exists():
    st.warning("No user accounts found. Run `python setup_users.py` to create accounts, then restart the app.")
    st.stop()


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------
def show_login():
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            f"## 📦 PO Extractor "
            f"<span style='font-size:0.55em; color:#888; font-weight:normal;'>"
            f"v{APP_VERSION}</span>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="your username")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

        if submitted:
            if verify_password(username, password):
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.results = None
                st.session_state.parse_log = []
                st.rerun()
            else:
                st.error("Incorrect username or password.")


# ---------------------------------------------------------------------------
# Change password — sidebar form
# ---------------------------------------------------------------------------
def _show_change_password_sidebar():
    with st.form("cp_form", clear_on_submit=True):
        old  = st.text_input("Current password", type="password")
        new1 = st.text_input("New password", type="password")
        new2 = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Save", type="primary", use_container_width=True)
    if submitted:
        if not new1:
            st.error("New password cannot be empty.")
        elif new1 != new2:
            st.error("Passwords do not match.")
        elif not change_password(st.session_state.username, old, new1):
            st.error("Current password is incorrect.")
        else:
            st.success("Password changed.")


# ---------------------------------------------------------------------------
# Main app page
# ---------------------------------------------------------------------------
def show_main():
    # ---- Sidebar ----
    with st.sidebar:
        st.markdown("### 📦 PO Extractor")
        st.caption(f"v{APP_VERSION}")
        st.divider()
        st.markdown(f"👤 **{st.session_state.username}**")
        with st.expander("🔑 Change Password"):
            _show_change_password_sidebar()
        st.divider()
        if st.button("Sign Out", use_container_width=True):
            for k, v in [
                (SK.LOGGED_IN,     False),
                (SK.USERNAME,      None),
                (SK.RESULTS,       None),
                (SK.PARSE_LOG,     []),
                (SK.SE_RESULTS,    None),
                (SK.SE_LOG,        []),
                (SK.SE_CONTRACTS,  None),
                (SK.SE_IMAGE_CACHE, {}),
            ]:
                st.session_state[k] = v
            st.rerun()

        st.divider()
        # ── Language toggle ───────────────────────────────────────────────
        _lang_now = st.session_state.get(SK.UI_LANG, "en")
        _lang_label = "🌐 切换中文" if _lang_now == "en" else "🌐 Switch to EN"
        if st.button(_lang_label, use_container_width=True, key="lang_toggle"):
            _new_lang = "zh" if _lang_now == "en" else "en"
            st.session_state[SK.UI_LANG] = _new_lang
            # Invalidate the i18n cache for the new language so it is
            # rebuilt from DB on first render after the toggle.
            from ui.i18n import clear_cache as _clear_i18n
            _clear_i18n(_new_lang)
            st.rerun()
        st.caption("中文" if _lang_now == "zh" else "English")

    # ---- Tabs ----
    admin_mode = is_admin(st.session_state.username)
    tab_labels = ["📋 GIII", "🛍 Sky East", "🧵 Fabric DB", "📐 Fabric Mapping", "🎨 Colors", "📊 Summary"]
    if admin_mode:
        tab_labels.append("⚙️ Admin")
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        _show_smart_upload_tab()
    with tabs[1]:
        _show_sky_east_tab()
    with tabs[2]:
        _show_fabric_db_tab()
    with tabs[3]:
        _show_fabric_mapping_tab()
    with tabs[4]:
        _show_color_translation_tab()
    with tabs[5]:
        _show_summary_tab(user_cos=get_user_companies(st.session_state.username),
                          admin_mode=admin_mode)
    if admin_mode:
        with tabs[6]:
            _show_admin_panel()


# -- Summary tab ---------------------------------------------------------


def _show_summary_tab(user_cos: list[str], admin_mode: bool) -> None:
    from ui.summary_view import show_summary_tab
    show_summary_tab(user_cos=user_cos, admin_mode=admin_mode)


def _show_admin_panel():
    (admin_tab_users, admin_tab_cos, admin_tab_schema, admin_tab_sizes,
     admin_tab_tpl, admin_tab_pipe, admin_tab_bsr, admin_tab_smtp,
     admin_tab_i18n, admin_tab_settings) = st.tabs(
        ["👤 Users", "🏢 Companies", "📋 Column Mapping", "📐 Size Order",
         "📄 Templates", "🧩 Pipeline Layouts", "🚢 船样要求", "📧 Email",
         "🌐 Translations", "⚙️ Settings"]
    )

    with admin_tab_cos:
        _show_company_admin()

    with admin_tab_users:
        _show_user_admin()

    with admin_tab_schema:
        _show_schema_editor()

    with admin_tab_sizes:
        _show_size_order_admin()

    with admin_tab_tpl:
        _show_templates_admin()

    with admin_tab_pipe:
        _show_pipeline_layout_admin()

    with admin_tab_bsr:
        _show_boat_sample_admin()

    with admin_tab_smtp:
        from ui.admin_smtp import show_smtp_admin
        show_smtp_admin()

    with admin_tab_i18n:
        from ui.admin_i18n import show_i18n_admin
        show_i18n_admin()

    with admin_tab_settings:
        from ui.admin_settings import show_settings_admin
        show_settings_admin()


# ---------------------------------------------------------------------------
# Admin: Size order management
# ---------------------------------------------------------------------------

def _show_size_order_admin():
    from ui.admin_size_order import show_size_order_admin
    show_size_order_admin()


# ---------------------------------------------------------------------------
# Admin: Buy-plan template management
# ---------------------------------------------------------------------------

def _show_templates_admin():
    from ui.admin_templates import show_templates_admin
    show_templates_admin()



def _show_pipeline_layout_admin():
    from ui.admin_pipeline_layout import show_pipeline_layout_admin
    show_pipeline_layout_admin()


def _show_boat_sample_admin():
    from ui.admin_boat_sample import show_boat_sample_admin
    show_boat_sample_admin()



def _show_schema_editor():
    from ui.admin_schema import show_schema_editor
    show_schema_editor(_SCHEMA_PATH, on_schema_change=_cached_schema.clear)



def _show_company_admin():
    from ui.admin_companies import show_company_admin
    show_company_admin()



def _show_user_admin():
    from ui.admin_users import show_user_admin
    show_user_admin()




# ---------------------------------------------------------------------------
# GIII Smart Upload tab
# ---------------------------------------------------------------------------


def _show_smart_upload_tab() -> None:
    from ui.giii_view import show_smart_upload_tab
    show_smart_upload_tab()


# ---------------------------------------------------------------------------
# Sky East Orders tab
# ---------------------------------------------------------------------------


def _show_sky_east_tab() -> None:
    from ui.sky_east_view import show_sky_east_tab
    show_sky_east_tab()




# ---------------------------------------------------------------------------
# Fabric DB tab
# ---------------------------------------------------------------------------


def _show_fabric_db_tab() -> None:
    from ui.fabric_db_view import show_fabric_db_tab
    show_fabric_db_tab()


def _show_fabric_mapping_tab() -> None:
    from ui.fabric_mapping_view import show_fabric_mapping_tab
    show_fabric_mapping_tab()


# ---------------------------------------------------------------------------
# Color Translation Tab
# ---------------------------------------------------------------------------


def _show_color_translation_tab() -> None:
    from ui.color_translation_view import show_color_translation_tab
    show_color_translation_tab()



# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if st.session_state.logged_in:
    show_main()
else:
    show_login()
