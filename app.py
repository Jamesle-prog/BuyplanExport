"""Threadline — Streamlit UI."""
import os
import sys

# Cap the BLAS thread pools BEFORE anything imports numpy — the pools and
# their per-thread buffers are allocated at import time and can't be resized
# afterwards. On a many-core box (28 here) that reserves a substantial block
# for an app that does dataframe work, not linear algebra, and on a machine
# near its commit limit it is the allocation that fails: numpy aborts the
# process with "OpenBLAS error: Memory allocation still failed after 10
# retries". Set here rather than in the launch command so the app is robust
# however it is started. An explicit value in the environment still wins.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS",
             "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "4")

import streamlit as st

APP_VERSION = "2.125.5"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth.license import validate_license
from auth.companies import ensure_defaults_seeded
from auth.users import (
    MODULE_SKY_EAST, MODULE_SKY_EAST_BUYPLAN,
    get_user_companies, get_user_modules, is_admin, user_exists,
)
from po_extractor.config import (
    SCHEMA_PATH as _SCHEMA_PATH_CFG, APP_NAME,
)
from ui.session_keys import SK
from ui.i18n import t

# Seed default companies on startup (idempotent)
ensure_defaults_seeded()

# Pre-load bcrypt / pandas / openpyxl / the stores on a background thread so
# the FIRST sign-in after a server start doesn't pay ~1 s (several seconds
# under Windows antivirus) of imports on the click.  No-op after the first
# run in a process; see ui/warmup.py.
from ui.warmup import warm_up as _warm_up
_warm_up()

_SCHEMA_PATH = _SCHEMA_PATH_CFG


# ── Live output schema (editable via Admin UI) ────────────────────────────────

# Live schema cache: ui/schema_labels.py (one cache shared by every tab; the
# schema editor clears it on save). Heavy imports stay inside its functions,
# so the login page never pays for them.
from ui.schema_labels import cached_schema as _cached_schema


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"{APP_NAME} v{APP_VERSION}",
    page_icon="🧵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
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

/* ── Multiselect dropdown checkboxes (all st.multiselect widgets) ─ */
[data-baseweb="menu"] [role="option"] {
    padding-left: 2.5rem !important;
    position: relative;
}
[data-baseweb="menu"] [role="option"]::before {
    content: '';
    position: absolute;
    left: 0.55rem;
    top: 50%;
    transform: translateY(-50%);
    width: 1rem;
    height: 1rem;
    border: 1.5px solid #9ca3af;
    border-radius: 3px;
    background: #fff;
    box-sizing: border-box;
    pointer-events: none;
}
[data-baseweb="menu"] [role="option"][aria-selected="true"]::before {
    content: '✓';
    background: #ff4b4b;
    border-color: #ff4b4b;
    color: #fff;
    font-size: 0.65rem;
    font-weight: 700;
    text-align: center;
    line-height: 1rem;
}
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
    (SK.SE_PROGRESS_LKUP, None),  # ProgressLookup instance
    (SK.SE_FABRIC_LOOKUP, None),  # fabric lookup cache
    (SK.SE_MASKED_ZIP,   None),   # masked zip bytes
    (SK.SE_IMAGES_DIR,   ""),     # local images folder path
    (SK.SE_DL_BYTES,     None),   # generated download bytes
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
    # Production Tracking
    (SK.PT_SELECTED_EDIT,  None),   # int — record id selected in Edit tab
    (SK.PT_DELETE_CONFIRM, False),  # bool — delete confirmation shown
    (SK.PT_ACTIVE_TAB,     0),      # int — active sub-tab (0 = Tracking Grid)
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
# Login page + change-password form live in ui/login_view.py (imported lazily
# in the router / sidebar so a signed-in rerun never pays for the login CSS).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main app page
# ---------------------------------------------------------------------------
def show_main():
    # ---- Sidebar ----
    with st.sidebar:
        st.markdown(f"### 🧵 {APP_NAME}")
        st.caption(f"v{APP_VERSION}")
        st.divider()
        # ── CPRS server status (at-a-glance; cached health probe) ─────────
        from ui.cprs_status import render_sidebar_cprs_status
        render_sidebar_cprs_status()
        st.divider()
        st.markdown(f"👤 **{st.session_state.username}**")
        with st.expander(f"🔑 {t('Change Password')}"):
            from ui.login_view import show_change_password_sidebar
            show_change_password_sidebar()
        st.divider()
        if st.button(t("Sign Out"), use_container_width=True):
            for k, v in [
                (SK.LOGGED_IN,        False),
                (SK.USERNAME,         None),
                # GIII
                (SK.RESULTS,          None),
                (SK.PARSE_LOG,        []),
                (SK.HISTORY_RESULTS,  None),
                (SK.HISTORY_BP_BYTES, None),
                (SK.GIII_MAPPING,     None),
                # Sky East — processing
                (SK.SE_RESULTS,       None),
                (SK.SE_LOG,           []),
                (SK.SE_CONTRACTS,     None),
                (SK.SE_IMAGE_CACHE,   {}),
                (SK.SE_PROGRESS_LKUP, None),
                (SK.SE_FABRIC_LOOKUP, None),
                (SK.SE_MASKED_ZIP,    None),
                # Sky East — generated files
                (SK.SE_DL_BYTES,      None),
                (SK.SE_DL_FNAME,      None),
                (SK.SE_DL_MIME,       None),
                (SK.SE_WL_BYTES,      None),
                (SK.SE_WL_FNAME,      None),
                (SK.SE_WL_PENDING,    None),
                (SK.SE_BP_BYTES,      None),
                (SK.SE_BP_NAME,       None),
                (SK.SE_NK_BYTES,      None),
                (SK.SE_NK_COUNT,      0),
                (SK.SE_NK_REASON,     None),
                (SK.SE_BP_CMP,        None),
                # Color source resets to admin default on next render
                (SK.SE_COLOR_SOURCE,  None),
                # GIII fax/portal extraction sections
                (SK.GIII_MSG_RESULTS,   None),
                (SK.GIII_MSG_SIG,       None),
                (SK.GIII_KL_RESULTS,    None),
                (SK.GIII_KL_SIG,        None),
                (SK.GIII_TKEU_RESULTS,  None),
                (SK.GIII_TKEU_SIG,      None),
                (SK.GIII_IN_RESULTS,    None),
                (SK.GIII_IN_SIG,        None),
                (SK.GIII_IN_KL_RESULTS, None),
                (SK.GIII_IN_KL_SIG,     None),
                (SK.GIII_MASTER_DL_BYTES, None),
                (SK.GIII_MASTER_DL_FNAME, None),
            ]:
                st.session_state[k] = v
            # Clear bare-string result/download keys not in the SK enum, so
            # the next user on this browser session never sees the previous
            # user's generated outputs (Reports tab + fax smart-extract).
            for _raw in ("_se_bp_prog_fp",
                         "rpt_all_results", "rpt_cp_bytes", "rpt_ps_bytes",
                         "rpt_kl_bytes", "rpt_bp_bytes", "rpt_cprs_bp_bytes",
                         "rpt_cprs_preview", "rpt_cprs_warns",
                         "smart_results", "excel_results"):
                st.session_state.pop(_raw, None)
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

        st.divider()
        # ── Memory management ─────────────────────────────────────────────
        from ui.memory import render_sidebar_memory
        render_sidebar_memory()

    # ---- Tabs ----
    admin_mode = is_admin(st.session_state.username)
    user_modules = get_user_modules(st.session_state.username)  # [] = unrestricted
    _buyplan_only = (
        MODULE_SKY_EAST_BUYPLAN in user_modules
        and MODULE_SKY_EAST not in user_modules
    )

    def _allowed(module_key: str) -> bool:
        if not user_modules:
            return True
        if module_key == "sky_east":
            return MODULE_SKY_EAST in user_modules or MODULE_SKY_EAST_BUYPLAN in user_modules
        return module_key in user_modules

    # Tab labels are display-only (st.tabs returns objects used positionally,
    # dispatch/visibility is keyed by the `key` field), so translating the
    # label text is safe.  Emoji stays outside t().
    _all_tabs = [
        ("giii",           f"📋 {t('GIII')}",           lambda: _show_smart_upload_tab()),
        ("sky_east",       f"🛍 {t('Sky East')}",       lambda: _show_sky_east_tab(restrict_to_buyplan=_buyplan_only)),
        ("upc_check",      f"📷 {t('UPC Check')}",      lambda: _show_upc_check_tab()),
        ("fabric_db",      f"🧵 {t('Fabric DB')}",      lambda: _show_fabric_db_tab()),
        ("reference_data", f"📐 {t('Reference Data')}", lambda: _show_fabric_mapping_tab()),
        ("colors",         f"🎨 {t('Colors')}",         lambda: _show_color_translation_tab()),
        ("summary",        f"📊 {t('Summary')}",        lambda: _show_summary_tab(
            user_cos=get_user_companies(st.session_state.username), admin_mode=admin_mode)),
        ("tracking",       f"🏭 {t('Tracking')}",       lambda: _show_production_tracking_tab(
            user_cos=get_user_companies(st.session_state.username), admin_mode=admin_mode)),
        ("cmpt",           f"📄 {t('CMPT')}",           lambda: _show_cmpt_tab(admin_mode=admin_mode)),
        ("email",          f"📧 {t('Email')}",          lambda: _show_email_tab(admin_mode=admin_mode)),
        ("cutting_plan",   f"✂️ {t('Cutting Plan')}",   lambda: _show_cutting_plan_tab()),
        ("settlement",     f"💰 {t('Settlement')}",     lambda: _show_settlement_tab()),
        ("fabric_condition", f"📏 {t('Fabric Condition')}", lambda: _show_fabric_condition_tab()),
        ("releases",       f"🔖 {t('Releases')}",       lambda: _show_changelog_tab()),
    ]
    _visible_tabs = [(label, fn) for key, label, fn in _all_tabs if _allowed(key)]
    tab_labels = [label for label, _ in _visible_tabs]
    if admin_mode:
        tab_labels.append(f"⚙️ {t('Admin')}")

    # Only the SELECTED section's body runs.
    #
    # This was st.tabs, which executes every tab body on every script run —
    # @st.fragment does not defer that, it only narrows later reruns. So one
    # page load was rendering all ~12 sections plus the whole admin panel:
    # every list query, DataFrame and table, almost all of it never looked at.
    # A single-select nav means one page load does one section's work.
    _NAV_KEY = "main_nav"
    # Labels are translated, so they change with the language toggle — drop a
    # stored value that is no longer an option or the widget raises.
    if st.session_state.get(_NAV_KEY) not in tab_labels:
        st.session_state[_NAV_KEY] = tab_labels[0]
    active = st.segmented_control(
        t("Section"), tab_labels, key=_NAV_KEY, label_visibility="collapsed")
    if active not in tab_labels:      # deselected — keep showing something
        active = st.session_state[_NAV_KEY]

    # Dispatch positionally, the way st.tabs did — label text is translated and
    # must never be the thing that decides which section runs.
    _idx = tab_labels.index(active)
    if admin_mode and _idx == len(tab_labels) - 1:
        _show_admin_panel()
    else:
        _visible_tabs[_idx][1]()


# -- Summary tab ---------------------------------------------------------


@st.fragment
def _show_summary_tab(user_cos: list[str], admin_mode: bool) -> None:
    from ui.summary_view import show_summary_tab
    show_summary_tab(user_cos=user_cos, admin_mode=admin_mode)


@st.fragment
def _show_production_tracking_tab(user_cos: list[str], admin_mode: bool) -> None:
    from ui.production_tracking_view import show_production_tracking_tab
    from auth.users import get_user_factories
    show_production_tracking_tab(
        user_cos=user_cos,
        username=st.session_state.username,
        admin_mode=admin_mode,
        user_factories=get_user_factories(st.session_state.username),
    )


@st.fragment
def _show_cmpt_tab(admin_mode: bool) -> None:
    from ui.cmpt_view import show_cmpt_tab
    show_cmpt_tab(username=st.session_state.username, admin_mode=admin_mode)


@st.fragment
def _show_email_tab(admin_mode: bool) -> None:
    from ui.email_view import show_email_tab
    show_email_tab(username=st.session_state.username, admin_mode=admin_mode)


@st.fragment
def _show_cutting_plan_tab() -> None:
    from ui.cutting_plan import show_cutting_plan_tab
    show_cutting_plan_tab()


@st.fragment
def _show_settlement_tab() -> None:
    from ui.settlement import show_settlement_tab
    show_settlement_tab()


@st.fragment
def _show_fabric_condition_tab() -> None:
    from ui.fabric_condition import show_fabric_condition_tab
    show_fabric_condition_tab()


def _show_admin_panel():
    # Badge the Factories tab with the count of unresolved factory names so an
    # admin sees at a glance that loaded POs introduced names needing review.
    try:
        from ui.stores import get_factory_registry_store
        _fac_pending = get_factory_registry_store().unresolved_count()
    except Exception:
        _fac_pending = 0
    _fac_label = f"🏭 {t('Factories')}" + (f" ({_fac_pending})" if _fac_pending else "")

    def _admin_smtp():
        from ui.admin_smtp import show_smtp_admin
        show_smtp_admin()

    def _admin_i18n():
        from ui.admin_i18n import show_i18n_admin
        show_i18n_admin()

    def _admin_settings():
        from ui.admin_settings import show_settings_admin
        show_settings_admin()

    def _admin_factories():
        from ui.admin_factories import show_factory_admin
        show_factory_admin()

    def _admin_login_log():
        from ui.admin_login_log import show_login_log_admin
        show_login_log_admin()

    # Same story as the main nav: st.tabs ran all twelve of these panels on
    # every admin render — including the translations editor (1,500+ rows) and
    # the fabric/user tables. Only the chosen panel runs now.
    _panels = [
        (f"👤 {t('Users')}",           _show_user_admin),
        (f"🏢 {t('Companies')}",       _show_company_admin),
        (_fac_label,                   _admin_factories),
        (f"📋 {t('Column Mapping')}",  _show_schema_editor),
        (f"📐 {t('Size Order')}",      _show_size_order_admin),
        (f"📄 {t('Templates')}",       _show_templates_admin),
        (f"🧩 {t('Pipeline Layouts')}", _show_pipeline_layout_admin),
        (f"🚢 {t('船样要求')}",         _show_boat_sample_admin),
        (f"📧 {t('Email')}",           _admin_smtp),
        (f"🌐 {t('Translations')}",    _admin_i18n),
        (f"🔐 {t('Login Log')}",       _admin_login_log),
        (f"⚙️ {t('Settings')}",        _admin_settings),
    ]
    _labels = [lbl for lbl, _ in _panels]
    _KEY = "admin_nav"
    # The factories label carries a live count and every label is translated,
    # so a stored value can go stale — fall back rather than raise.
    if st.session_state.get(_KEY) not in _labels:
        st.session_state[_KEY] = _labels[0]
    _active = st.segmented_control(
        t("Admin section"), _labels, key=_KEY, label_visibility="collapsed")
    if _active not in _labels:
        _active = st.session_state[_KEY]
    _panels[_labels.index(_active)][1]()


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


@st.fragment
def _show_smart_upload_tab() -> None:
    from ui.giii_view import show_smart_upload_tab
    show_smart_upload_tab()


# ---------------------------------------------------------------------------
# Sky East Orders tab
# ---------------------------------------------------------------------------


@st.fragment
def _show_sky_east_tab(restrict_to_buyplan: bool = False) -> None:
    from ui.sky_east_view import show_sky_east_tab
    show_sky_east_tab(restrict_to_buyplan=restrict_to_buyplan)


@st.fragment
def _show_upc_check_tab() -> None:
    from ui.upc_check import show_upc_check_tab
    show_upc_check_tab()




# ---------------------------------------------------------------------------
# Fabric DB tab
# ---------------------------------------------------------------------------


@st.fragment
def _show_fabric_db_tab() -> None:
    from ui.fabric_db_view import show_fabric_db_tab
    show_fabric_db_tab()


@st.fragment
def _show_fabric_mapping_tab() -> None:
    from ui.fabric_mapping_view import show_fabric_mapping_tab
    show_fabric_mapping_tab()


# ---------------------------------------------------------------------------
# Color Translation Tab
# ---------------------------------------------------------------------------


@st.fragment
def _show_color_translation_tab() -> None:
    from ui.color_translation_view import show_color_translation_tab
    show_color_translation_tab()


# ---------------------------------------------------------------------------
# Changelog / Releases tab
# ---------------------------------------------------------------------------


@st.fragment
def _show_changelog_tab() -> None:
    from ui.changelog_view import show_changelog_tab
    show_changelog_tab()



# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
if st.session_state.logged_in:
    show_main()
else:
    from ui.login_view import show_login
    show_login(APP_VERSION)
