"""Threadline — Streamlit UI."""
import os
import sys

import streamlit as st

APP_VERSION = "2.95.0"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auth.license import validate_license
from auth.companies import ensure_defaults_seeded
from auth.users import (
    MODULE_SKY_EAST, MODULE_SKY_EAST_BUYPLAN,
    change_password, get_user_companies, get_user_modules, is_admin,
    user_exists, verify_password,
)
from po_extractor.config import (
    SCHEMA_PATH as _SCHEMA_PATH_CFG, CACHE_TTL_SECONDS, APP_NAME, APP_TAGLINE,
)
from ui.session_keys import SK
from ui.i18n import t

# Seed default companies on startup (idempotent)
ensure_defaults_seeded()

_SCHEMA_PATH = _SCHEMA_PATH_CFG


# ── Live output schema (editable via Admin UI) ────────────────────────────────

# Live schema helpers — implementation in po_extractor.ui_helpers.schema.
# Imported lazily: po_extractor.ui_helpers transitively pulls pandas + numpy
# + openpyxl + PIL (~0.7s warm, multi-second on a cold start with AV
# scanning), and nothing pre-login needs it — a module-level import made the
# LOGIN page pay that cost on every fresh server start.
def _load_live_schema() -> list[dict]:
    from po_extractor.ui_helpers import load_live_schema as _impl
    return _impl(_SCHEMA_PATH)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def _cached_schema() -> list[dict]:
    """Cached live schema — refreshes every 60 s or when cleared explicitly."""
    return _load_live_schema()


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
# Login throttle — the app is reachable from the network, so failed sign-ins
# must cost something.  Process-wide (module-level, shared by all sessions and
# threads — a per-session counter would be trivially bypassed by dropping the
# session).  After _LOGIN_FAIL_THRESHOLD failures a key locks out with
# exponential backoff; a coarser global brake catches username spraying.
# ---------------------------------------------------------------------------
import threading as _threading
import time as _time

_LOGIN_GUARD_LOCK = _threading.Lock()
_LOGIN_FAILURES: dict[str, tuple[int, float]] = {}   # key → (fails, locked_until)
_LOGIN_GLOBAL_KEY = "\x00global"

_LOGIN_FAIL_THRESHOLD   = 5      # per-username fails before lockout
_LOGIN_BASE_LOCK_S      = 60.0   # first lockout, doubles per extra fail
_LOGIN_MAX_LOCK_S       = 900.0
_LOGIN_GLOBAL_THRESHOLD = 30     # total fails across all usernames
_LOGIN_GLOBAL_LOCK_S    = 120.0


def _login_lock_remaining(key: str) -> int:
    """Seconds left on the lockout for *key* (0 = not locked)."""
    with _LOGIN_GUARD_LOCK:
        _count, until = _LOGIN_FAILURES.get(key, (0, 0.0))
        remaining = until - _time.time()
    return int(remaining) + 1 if remaining > 0 else 0


def _login_failed(key: str, threshold: int, base_lock_s: float, max_lock_s: float) -> None:
    with _LOGIN_GUARD_LOCK:
        count, _until = _LOGIN_FAILURES.get(key, (0, 0.0))
        count += 1
        lock_s = 0.0
        if count >= threshold:
            lock_s = min(base_lock_s * (2 ** (count - threshold)), max_lock_s)
        _LOGIN_FAILURES[key] = (count, _time.time() + lock_s)


def _login_succeeded(key: str) -> None:
    with _LOGIN_GUARD_LOCK:
        _LOGIN_FAILURES.pop(key, None)


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------
# Scoped to the login screen only (injected inside show_login, so it never
# affects the main app's forms/layout). A bold, friendly single-accent look —
# warm gradient backdrop, one big rounded card, pill inputs and button.
# Theme-aware via prefers-color-scheme, which Streamlit's default theme follows.
_LOGIN_CSS = """
<style>
/* Warm gradient backdrop across the whole viewport (login page only). */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(1100px 520px at 15% -10%, #ffe3ec 0%, rgba(255,227,236,0) 60%),
        radial-gradient(1000px 560px at 95% 8%, #ffe9dd 0%, rgba(255,233,221,0) 55%),
        linear-gradient(180deg, #fff6f8 0%, #fff 62%);
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppViewContainer"] .block-container {
    max-width: 460px; padding-top: 8vh; padding-bottom: 5rem;
}

/* Brand header */
.tl-brand { text-align: center; margin: 0 0 1.6rem; }
.tl-logo {
    width: 84px; height: 84px; margin: 0 auto 1.1rem;
    display: flex; align-items: center; justify-content: center;
    font-size: 42px; border-radius: 26px;
    background: linear-gradient(135deg, #ff2e74 0%, #ff6a5b 100%);
    box-shadow: 0 16px 34px rgba(255,46,116,0.40);
}
.tl-title {
    font-size: 2.5rem; font-weight: 800; margin: 0; letter-spacing: -0.03em;
    color: #16121a; line-height: 1.05;
}
.tl-sub {
    color: #7a6b73; font-size: 1.05rem; margin-top: 0.55rem; font-weight: 500;
}

/* The form becomes one big friendly card. */
div[data-testid="stForm"] {
    border: none; border-radius: 26px;
    padding: 2.1rem 2rem 1.6rem;
    background: #ffffff;
    box-shadow: 0 24px 60px rgba(255,46,116,0.14), 0 4px 14px rgba(20,20,43,0.06);
}
div[data-testid="stForm"] label p { font-weight: 650; font-size: 0.9rem; color:#4b4048; }
div[data-testid="stForm"] input {
    border-radius: 999px !important; padding: 0.7rem 1.1rem !important;
    background: #f8f6f7 !important; border: 1.5px solid #f0eaed !important;
    font-size: 0.98rem !important;
}
div[data-testid="stForm"] input:focus {
    border-color: #ff2e74 !important;
    box-shadow: 0 0 0 3px rgba(255,46,116,0.14) !important;
}
div[data-testid="stFormSubmitButton"] button {
    border-radius: 999px; font-weight: 750; font-size: 1.02rem;
    padding: 0.7rem 1rem; margin-top: 0.35rem;
    border: none; color: #fff;
    background: linear-gradient(135deg, #ff2e74 0%, #ff6a5b 100%);
    box-shadow: 0 12px 26px rgba(255,46,116,0.36);
    transition: filter .15s ease, transform .06s ease, box-shadow .15s ease;
}
div[data-testid="stFormSubmitButton"] button:hover {
    filter: brightness(1.05); box-shadow: 0 16px 32px rgba(255,46,116,0.44);
}
div[data-testid="stFormSubmitButton"] button:active { transform: translateY(1px); }

.tl-hi { font-size: 1.15rem; font-weight: 750; color:#16121a; margin: 0 0 0.2rem; }
.tl-hi-sub { color:#8a7c83; font-size:0.86rem; margin: 0 0 1rem; }
.tl-foot {
    text-align: center; color: #b6a9b0; font-size: 0.76rem; margin-top: 1.5rem;
}
.tl-foot b { color:#8a7c83; font-weight:600; }

@media (prefers-color-scheme: dark) {
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(1100px 520px at 15% -10%, #2a1620 0%, rgba(42,22,32,0) 60%),
            radial-gradient(1000px 560px at 95% 8%, #241a1c 0%, rgba(36,26,28,0) 55%),
            linear-gradient(180deg, #14121a 0%, #0f0e14 62%);
    }
    .tl-title { color: #f4eef2; }
    .tl-sub { color: #b9a9b2; }
    .tl-hi { color: #f4eef2; }
    div[data-testid="stForm"] {
        background: #191620;
        box-shadow: 0 24px 60px rgba(0,0,0,0.5);
    }
    div[data-testid="stForm"] input {
        background: #221d29 !important; border-color: #2f2833 !important;
        color: #f4eef2 !important;
    }
}
</style>
"""


def show_login():
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="tl-brand">
            <div class="tl-logo">🧵</div>
            <div class="tl-title">{APP_NAME}</div>
            <div class="tl-sub">{t(APP_TAGLINE)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("login_form"):
        st.markdown(
            f"<div class='tl-hi'>{t('Welcome back 👋')}</div>"
            f"<div class='tl-hi-sub'>{t('Sign in to pick up where you left off.')}</div>",
            unsafe_allow_html=True,
        )
        username = st.text_input(t("Username"), placeholder=t("your username"))
        password = st.text_input(t("Password"), type="password",
                                 placeholder="••••••••")
        submitted = st.form_submit_button(t("Sign In"), type="primary",
                                          use_container_width=True)

    st.markdown(
        f"<div class='tl-foot'>🔒 {t('Authorized users only')} · "
        f"<b>{APP_NAME}</b> v{APP_VERSION}</div>",
        unsafe_allow_html=True,
    )

    if submitted:
        uname_key = (username or "").strip().lower()
        wait = max(
            _login_lock_remaining(uname_key),
            _login_lock_remaining(_LOGIN_GLOBAL_KEY),
        )
        if wait:
            st.error(f"{t('Too many failed attempts. Try again in')} {wait} s.")
        elif verify_password(username, password):
            _login_succeeded(uname_key)
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.results = None
            st.session_state.parse_log = []
            st.rerun()
        else:
            _login_failed(uname_key, _LOGIN_FAIL_THRESHOLD,
                          _LOGIN_BASE_LOCK_S, _LOGIN_MAX_LOCK_S)
            _login_failed(_LOGIN_GLOBAL_KEY, _LOGIN_GLOBAL_THRESHOLD,
                          _LOGIN_GLOBAL_LOCK_S, _LOGIN_GLOBAL_LOCK_S)
            st.error(t("Incorrect username or password."))


# ---------------------------------------------------------------------------
# Change password — sidebar form
# ---------------------------------------------------------------------------
def _show_change_password_sidebar():
    with st.form("cp_form", clear_on_submit=True):
        old  = st.text_input(t("Current password"), type="password")
        new1 = st.text_input(t("New password"), type="password")
        new2 = st.text_input(t("Confirm new password"), type="password")
        submitted = st.form_submit_button(t("Save"), type="primary", use_container_width=True)
    if submitted:
        if not new1:
            st.error(t("New password cannot be empty."))
        elif new1 != new2:
            st.error(t("Passwords do not match."))
        elif not change_password(st.session_state.username, old, new1):
            st.error(t("Current password is incorrect."))
        else:
            st.success(t("Password changed."))


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
            _show_change_password_sidebar()
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
        ("releases",       f"🔖 {t('Releases')}",       lambda: _show_changelog_tab()),
    ]
    _visible_tabs = [(label, fn) for key, label, fn in _all_tabs if _allowed(key)]
    tab_labels = [label for label, _ in _visible_tabs]
    if admin_mode:
        tab_labels.append(f"⚙️ {t('Admin')}")
    tabs = st.tabs(tab_labels)

    for tab, (_, fn) in zip(tabs, _visible_tabs):
        with tab:
            fn()
    if admin_mode:
        with tabs[-1]:
            _show_admin_panel()


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


def _show_admin_panel():
    # Badge the Factories tab with the count of unresolved factory names so an
    # admin sees at a glance that loaded POs introduced names needing review.
    try:
        from ui.stores import get_factory_registry_store
        _fac_pending = get_factory_registry_store().unresolved_count()
    except Exception:
        _fac_pending = 0
    _fac_label = f"🏭 {t('Factories')}" + (f" ({_fac_pending})" if _fac_pending else "")

    (admin_tab_users, admin_tab_cos, admin_tab_fac, admin_tab_schema,
     admin_tab_sizes, admin_tab_tpl, admin_tab_pipe, admin_tab_bsr,
     admin_tab_smtp, admin_tab_i18n, admin_tab_settings) = st.tabs(
        [f"👤 {t('Users')}", f"🏢 {t('Companies')}", _fac_label,
         f"📋 {t('Column Mapping')}",
         f"📐 {t('Size Order')}", f"📄 {t('Templates')}", f"🧩 {t('Pipeline Layouts')}",
         f"🚢 {t('船样要求')}", f"📧 {t('Email')}", f"🌐 {t('Translations')}",
         f"⚙️ {t('Settings')}"]
    )

    with admin_tab_cos:
        _show_company_admin()

    with admin_tab_fac:
        from ui.admin_factories import show_factory_admin
        show_factory_admin()

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
    show_login()
