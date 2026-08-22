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

APP_VERSION = "2.132.0"

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
    st.error(t("⛔ License error: {msg}").format(msg=license_msg))
    st.stop()

# ---------------------------------------------------------------------------
# Guard: no users yet → show setup prompt
# ---------------------------------------------------------------------------
if not user_exists():
    st.warning(t("No user accounts found. Run `python setup_users.py` to create accounts, then restart the app."))
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

# Sign-in lockout policy — values live in po_extractor.config so they're
# tunable in one place alongside the other cross-cutting constants.
from po_extractor.config import (
    LOGIN_FAIL_THRESHOLD    as _LOGIN_FAIL_THRESHOLD,
    LOGIN_BASE_LOCK_S       as _LOGIN_BASE_LOCK_S,
    LOGIN_MAX_LOCK_S        as _LOGIN_MAX_LOCK_S,
    LOGIN_GLOBAL_THRESHOLD  as _LOGIN_GLOBAL_THRESHOLD,
    LOGIN_GLOBAL_LOCK_S     as _LOGIN_GLOBAL_LOCK_S,
)


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
# affects the main app's forms/layout). Implements the "Threadline Login"
# design (claude.ai/design project "Login page redesign"): a split screen —
# left, a warm hero panel with the wordmark, headline, four-step journey
# strip (Client PO → Buy Plan → Production → Delivery) and a line-art
# atelier scene crossed by an animated thread; right, the sign-in form with
# a language pill. Bilingual via t(); dark-mode via prefers-color-scheme.
_LOGIN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Schibsted+Grotesk:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap');

:root {
    --tl-ink: #241a21; --tl-soft: #7a6b73; --tl-faint: #b6a9b0;
    --tl-hair: #f0e6ea; --tl-field: #fbf8f9; --tl-page: #ffffff;
    --tl-panel: linear-gradient(180deg, #fff6f9 0%, #fdf4ef 100%);
    --tl-circle: #ffffff; --tl-chip: #ffd3e2; --tl-dot: #d8ccd3;
    --tl-illu: 1;
}
@media (prefers-color-scheme: dark) {
    :root {
        --tl-ink: #f4eef2; --tl-soft: #b9a9b2; --tl-faint: #6f6069;
        --tl-hair: #3a2f3a; --tl-field: #211b29; --tl-page: #17131c;
        --tl-panel: linear-gradient(180deg, #1c1620 0%, #191419 100%);
        --tl-circle: rgba(255,46,116,0.08); --tl-chip: rgba(255,46,116,0.28);
        --tl-dot: #4a3c44;
        --tl-illu: 0.18;
    }
}

[data-testid="stHeader"] { display: none; }
[data-testid="stAppViewContainer"] { background: var(--tl-page); }
[data-testid="stAppViewContainer"] .block-container { max-width: 100%; padding: 0; }
[data-testid="stHorizontalBlock"] { gap: 0 !important; align-items: stretch; }

[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
    background: var(--tl-panel);
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
    background: var(--tl-page);
    border-left: 1px solid var(--tl-hair);
    padding: 26px clamp(24px, 4.5vw, 72px) 48px;
}
@media (max-width: 760px) {
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child { display: none; }
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child { border-left: none; }
}

/* ── Left hero panel ── */
.tl-hero {
    display: flex; flex-direction: column; min-height: 100vh;
    padding: 44px 56px 0; color: var(--tl-ink);
    font-family: 'Schibsted Grotesk', 'Noto Sans SC', sans-serif;
}
.tl-mark { display: flex; align-items: center; gap: 14px; }
.tl-logo {
    width: 44px; height: 44px; border-radius: 14px; font-size: 22px;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #ff2e74, #ff6a5b);
    box-shadow: 0 10px 26px rgba(255,46,116,0.28);
}
.tl-word {
    font-family: 'Bricolage Grotesque', 'Noto Sans SC', sans-serif;
    font-size: 24px; font-weight: 700; letter-spacing: -0.02em;
}
.tl-htitle {
    margin-top: clamp(28px, 5vh, 60px); max-width: 620px;
    font-family: 'Bricolage Grotesque', 'Noto Sans SC', sans-serif;
    font-size: clamp(30px, 3.2vw, 52px); line-height: 1.08;
    font-weight: 700; letter-spacing: -0.025em; text-wrap: balance;
}
.tl-hsub {
    margin-top: 14px; max-width: 52ch;
    font-size: clamp(14px, 1.1vw, 17px); line-height: 1.6; color: var(--tl-soft);
}
.tl-steps {
    margin-top: clamp(28px, 4.5vh, 52px);
    display: flex; align-items: flex-start; max-width: 620px;
}
.tl-step { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.tl-step-circle {
    width: clamp(50px, 4.2vw, 68px); height: clamp(50px, 4.2vw, 68px);
    border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--tl-circle); border: 1.5px solid var(--tl-chip); color: #ff2e74;
}
.tl-step-circle svg { width: 40%; height: 40%; }
.tl-step-label { font-size: clamp(12px, 0.95vw, 14px); font-weight: 700; white-space: nowrap; }
.tl-step-line {
    flex: 1; min-width: 20px; border-top: 2px dotted var(--tl-dot);
    margin-top: clamp(25px, 2.1vw, 34px);
}
.tl-illu { margin: 20px -56px 0; margin-top: auto; opacity: var(--tl-illu); }
.tl-illu svg { width: 100%; display: block; }
@keyframes tl-dash { to { stroke-dashoffset: -400; } }
@media (prefers-reduced-motion: reduce) { .tl-illu * { animation: none !important; } }

/* ── Right form panel ── */
div[class*="st-key-login_lang"] { display: flex; justify-content: flex-end; }
div[class*="st-key-login_lang"] button {
    border: 1.5px solid var(--tl-hair) !important; background: transparent !important;
    color: var(--tl-soft) !important; border-radius: 999px !important;
    font-weight: 600 !important; font-size: 13px !important;
    padding: 6px 15px !important; box-shadow: none !important;
}
div[class*="st-key-login_lang"] button:hover {
    border-color: #ff2e74 !important; color: #ff2e74 !important;
}

.tl-welcome {
    margin: clamp(14px, 9vh, 110px) auto 0; max-width: 380px;
    color: var(--tl-ink);
}
.tl-welcome h1 {
    font-family: 'Bricolage Grotesque', 'Noto Sans SC', sans-serif;
    font-size: 30px; font-weight: 700; letter-spacing: -0.02em; margin: 0;
    color: var(--tl-ink);
}
.tl-welcome p {
    margin: 8px 0 0; font-size: 14.5px; color: var(--tl-soft);
    font-family: 'Schibsted Grotesk', 'Noto Sans SC', sans-serif;
}

div[data-testid="stForm"] {
    border: none; background: transparent; padding: 0; box-shadow: none;
    max-width: 380px; margin: 22px auto 0;
}
div[data-testid="stForm"] label p {
    font-weight: 700 !important; font-size: 13px !important;
    color: var(--tl-soft) !important;
    font-family: 'Schibsted Grotesk', 'Noto Sans SC', sans-serif !important;
}
/* The field box is drawn on BaseWeb's wrapper, NOT on the <input>.
   Streamlit nests the input inside div[data-baseweb="input"], which draws a
   border of its own — so bordering the inner element as well produced two
   concentric rounded rectangles, obvious once focus turned them pink. One
   box, one border. Keeping it on the wrapper also puts the password reveal
   button inside the field instead of floating beside it. */
div[data-testid="stForm"] div[data-baseweb="input"] {
    border-radius: 14px !important;
    border: 1.5px solid var(--tl-hair) !important;
    background: var(--tl-field) !important;
    box-shadow: none !important;
    transition: border-color .15s, box-shadow .15s;
}
div[data-testid="stForm"] div[data-baseweb="input"]:focus-within {
    border-color: #ff2e74 !important;
    box-shadow: 0 0 0 3.5px rgba(255,46,116,0.14) !important;
}
/* Everything inside the box stays flat — no second border, no second fill. */
div[data-testid="stForm"] div[data-baseweb="base-input"],
div[data-testid="stForm"] input,
div[data-testid="stForm"] input:focus {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    outline: none !important;
}
div[data-testid="stForm"] input {
    color: var(--tl-ink) !important;
    padding: 13px 16px !important; font-size: 15px !important; font-weight: 500 !important;
    font-family: 'Schibsted Grotesk', 'Noto Sans SC', sans-serif !important;
}
div[data-testid="stFormSubmitButton"] button {
    width: 100%; border: none; border-radius: 14px; padding: 13px;
    color: #fff; font-weight: 700; font-size: 15.5px;
    font-family: 'Schibsted Grotesk', 'Noto Sans SC', sans-serif;
    background: linear-gradient(135deg, #ff2e74, #ff6a5b);
    box-shadow: 0 12px 26px rgba(255,46,116,0.30);
    transition: filter .15s ease, transform .06s ease;
}
div[data-testid="stFormSubmitButton"] button:hover { filter: brightness(1.06); }
div[data-testid="stFormSubmitButton"] button:active { transform: translateY(1px); }

[data-testid="stColumn"]:last-child [data-testid="stAlert"] {
    max-width: 380px; margin-left: auto; margin-right: auto;
}
.tl-foot {
    max-width: 380px; margin: 24px auto 0; text-align: center;
    font-size: 12.5px; color: var(--tl-faint);
}
.tl-foot b { color: var(--tl-soft); font-weight: 600; }
</style>
"""

# Journey-step icons from the design (24×24 stroke paths):
# document → buy-plan grid → factory → delivery truck.
_LOGIN_STEP_ICONS = [
    "M6 2 h9 l5 5 v15 H6 z M15 2 v5 h5 M9.5 12 h8 M9.5 16 h5",
    "M4 4 h16 v16 H4 z M4 10 h16 M10 4 v16",
    "M3 21 V9 l6 4 V9 l6 4 V4 h6 v17 z",
    "M1 7 h12 v9 H1 z M13 10 h5 l3 3 v3 h-8 M5.5 19 a2 2 0 1 0 .001 0 "
    "M18.5 19 a2 2 0 1 0 .001 0",
]

# The atelier line-art scene from the design file, verbatim: clouds, spool,
# garment rack with two hangers, dress form, sewing machine, parcel press and
# skyline — crossed by two dashed thread paths animated via @keyframes tl-dash.
_LOGIN_ILLUSTRATION = """
<svg viewBox="0 0 640 300" preserveAspectRatio="xMidYMax meet" aria-hidden="true">
  <g fill="none" stroke="#d5c3cc" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M84 104 q16 -20 40 -10 q8 -14 28 -7 q18 -7 27 7" opacity="0.5"></path>
    <path d="M488 76 q13 -16 33 -8 q16 -5 23 8" opacity="0.5"></path>
    <g opacity="0.4" stroke-width="1.6">
      <path d="M598 258 V190 h36 v68"></path>
      <path d="M608 202 h8 v8 h-8 z M622 202 h8 v8 h-8 z M608 220 h8 v8 h-8 z"></path>
    </g>
    <g fill="#ffffff">
      <rect x="34" y="228" width="74" height="30" rx="15"></rect>
      <circle cx="108" cy="243" r="15" fill="#f6e7ee"></circle>
      <path d="M108 243 a6 6 0 0 1 6 6" stroke-width="1.6"></path>
      <rect x="42" y="202" width="58" height="26" rx="13" fill="#f6e7ee"></rect>
      <circle cx="100" cy="215" r="13" fill="#ffffff"></circle>
      <path d="M100 215 a5 5 0 0 1 5 5" stroke-width="1.6"></path>
    </g>
    <path d="M136 132 V258 M324 132 V258" stroke-width="3"></path>
    <path d="M126 133 Q230 121 334 133" stroke-width="3"></path>
    <g fill="#f6e7ee">
      <path d="M180 128 a5 6 0 0 0 -5 6 l5 5 5 -5 a5 6 0 0 0 -5 -6 z" fill="none" stroke-width="1.6"></path>
      <path d="M180 139 L163 152 L197 152 Z" fill="none" stroke-width="1.6"></path>
      <path d="M167 152 C162 172 174 183 173 192 L187 192 C186 183 198 172 193 152 Z"></path>
      <path d="M173 192 C154 224 150 240 155 247 Q167 253 180 249 Q193 253 205 247 C210 240 206 224 187 192 Z"></path>
    </g>
    <g fill="#ffffff">
      <path d="M250 128 a5 6 0 0 0 -5 6 l5 5 5 -5 a5 6 0 0 0 -5 -6 z" fill="none" stroke-width="1.6"></path>
      <path d="M250 139 L231 153 L269 153 Z" fill="none" stroke-width="1.6"></path>
      <path d="M231 153 C226 156 222 196 226 214 L242 210 L242 222 Q250 226 258 222 L258 210 L274 214 C278 196 274 156 269 153 L258 156 L250 172 L242 156 Z"></path>
      <path d="M242 156 L250 172 L258 156" stroke-width="1.6" fill="none"></path>
      <circle cx="250" cy="184" r="1.6"></circle><circle cx="250" cy="196" r="1.6"></circle>
    </g>
    <g fill="#ffffff">
      <circle cx="375" cy="146" r="5"></circle>
      <path d="M362 166 C361 152 389 152 388 166 C393 184 387 200 375 207 C363 200 357 184 362 166 Z"></path>
      <path d="M375 156 V202 M363 180 Q375 187 387 180" stroke-width="1.2" opacity="0.7" fill="none"></path>
      <path d="M375 207 V240 M375 240 L359 258 M375 240 L391 258 M366 258 h18" fill="none"></path>
    </g>
    <g fill="#ffffff">
      <rect x="428" y="244" width="94" height="14" rx="5"></rect>
      <path d="M448 244 V206 Q448 194 460 194 H494 Q510 194 510 210 V244 Z"></path>
      <path d="M462 244 V218 H498 V244" fill="#fdf3f0"></path>
      <circle cx="504" cy="212" r="8" fill="#f6e7ee"></circle><circle cx="504" cy="212" r="3"></circle>
      <path d="M462 218 V232" stroke-width="1.6" fill="none"></path>
      <rect x="468" y="184" width="9" height="10" rx="2" fill="#f6e7ee"></rect>
    </g>
    <g fill="#ffffff">
      <rect x="556" y="208" width="44" height="9" rx="4.5"></rect>
      <rect x="556" y="249" width="44" height="9" rx="4.5"></rect>
      <rect x="563" y="217" width="30" height="32" fill="#f6e7ee"></rect>
      <path d="M563 225 h30 M563 233 h30 M563 241 h30" stroke-width="1.2" opacity="0.7" fill="none"></path>
    </g>
    <path d="M0 258 H640" stroke-width="3"></path>
    <path d="M112 258 q9 -11 22 0 M540 258 q9 -11 22 0" fill="#f6e7ee"></path>
    <circle cx="212" cy="252" r="5" fill="#ffffff" stroke-width="1.6"></circle>
    <circle cx="210.5" cy="252" r="0.7"></circle><circle cx="213.5" cy="252" r="0.7"></circle>
  </g>
  <g fill="none" stroke="#ff9dbf" stroke-width="1.8" stroke-linecap="round">
    <path d="M-20 48 C140 84 300 30 380 66 C440 92 452 150 465 194 C468 205 464 212 462 218" stroke-dasharray="7 9" style="animation:tl-dash 30s linear infinite;"></path>
    <path d="M462 232 C470 250 500 262 540 258 C562 256 574 240 570 217" stroke-dasharray="7 9" style="animation:tl-dash 30s linear infinite;"></path>
  </g>
</svg>
"""


def _login_hero_html() -> str:
    """Left hero panel: wordmark, headline, journey steps, illustration."""
    step_labels = [t("Client PO"), t("Buy Plan"), t("Production"), t("Delivery")]
    steps = []
    last = len(step_labels) - 1
    for i, (label, icon) in enumerate(zip(step_labels, _LOGIN_STEP_ICONS)):
        steps.append(
            "<div style='display:flex;align-items:flex-start;"
            + ("flex:1 1 0%;" if i < last else "flex:0 0 auto;") + "'>"
            "<div class='tl-step'>"
            "<div class='tl-step-circle'>"
            "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' "
            "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
            f"<path d='{icon}'/></svg></div>"
            f"<div class='tl-step-label'>{label}</div></div>"
            + ("<div class='tl-step-line'></div>" if i < last else "")
            + "</div>"
        )
    return (
        "<div class='tl-hero'>"
        f"<div class='tl-mark'><div class='tl-logo'>🧵</div>"
        f"<div class='tl-word'>{APP_NAME}</div></div>"
        f"<div class='tl-htitle'>{t(APP_TAGLINE)}</div>"
        f"<div class='tl-hsub'>{t('Client POs, buy plans, fabric, and factory progress — connected in one place.')}</div>"
        f"<div class='tl-steps'>{''.join(steps)}</div>"
        f"<div class='tl-illu'>{_LOGIN_ILLUSTRATION}</div>"
        "</div>"
    )


def _client_ip() -> str:
    """Best-effort client IP for the audit log — the forwarded address behind
    a reverse proxy, else "". Never raises: the log is a nice-to-have and must
    not break sign-in on a Streamlit build that lacks st.context.headers."""
    try:
        headers = getattr(st.context, "headers", None) or {}
        xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return (headers.get("X-Real-Ip") or headers.get("x-real-ip") or "").strip()
    except Exception:
        return ""


def _record_login(username: str, outcome: str, detail: str = "") -> None:
    """Append a sign-in event to the audit log. Lazy-imported and fully
    guarded so it never delays the login page or blocks a real sign-in."""
    try:
        from po_extractor.store import get_login_log_store
        get_login_log_store().record(
            username, outcome, detail=detail, ip=_client_ip())
    except Exception:
        pass


def show_login():
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)
    left, right = st.columns([1.05, 1])
    with left:
        st.markdown(_login_hero_html(), unsafe_allow_html=True)

    with right:
        # Language pill — same mechanics as the sidebar toggle, available
        # before sign-in so factory users land in their own language.
        _lang_now = st.session_state.get(SK.UI_LANG, "en")
        if st.button("🌐 " + ("中文" if _lang_now == "en" else "EN"),
                     key="login_lang"):
            _new_lang = "zh" if _lang_now == "en" else "en"
            st.session_state[SK.UI_LANG] = _new_lang
            from ui.i18n import clear_cache as _clear_i18n
            _clear_i18n(_new_lang)
            st.rerun()

        st.markdown(
            f"<div class='tl-welcome'><h1>{t('Welcome back')}</h1>"
            f"<p>{t('Sign in to pick up where you left off.')}</p></div>",
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            username = st.text_input(t("Username"), placeholder=t("your username"))
            password = st.text_input(t("Password"), type="password",
                                     placeholder="••••••••")
            submitted = st.form_submit_button(t("Sign In"), type="primary",
                                              use_container_width=True)

        if submitted:
            uname_key = (username or "").strip().lower()
            wait = max(
                _login_lock_remaining(uname_key),
                _login_lock_remaining(_LOGIN_GLOBAL_KEY),
            )
            if wait:
                _record_login(username, "locked", f"locked {wait}s")
                st.error(f"{t('Too many failed attempts. Try again in')} {wait} s.")
            elif verify_password(username, password):
                _login_succeeded(uname_key)
                _record_login(username, "success")
                st.session_state.logged_in = True
                st.session_state[SK.USERNAME] = username
                st.session_state.results = None
                st.session_state.parse_log = []
                st.rerun()
            else:
                _login_failed(uname_key, _LOGIN_FAIL_THRESHOLD,
                              _LOGIN_BASE_LOCK_S, _LOGIN_MAX_LOCK_S)
                _login_failed(_LOGIN_GLOBAL_KEY, _LOGIN_GLOBAL_THRESHOLD,
                              _LOGIN_GLOBAL_LOCK_S, _LOGIN_GLOBAL_LOCK_S)
                _record_login(username, "failed", "wrong username or password")
                st.error(t("Incorrect username or password."))

        st.markdown(
            f"<div class='tl-foot'>🔒 {t('Authorized users only')} · "
            f"<b>{APP_NAME}</b> v{APP_VERSION}</div>",
            unsafe_allow_html=True,
        )


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
        elif not change_password(st.session_state[SK.USERNAME], old, new1):
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
        st.markdown(f"👤 **{st.session_state[SK.USERNAME]}**")
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
    admin_mode = is_admin(st.session_state[SK.USERNAME])
    user_modules = get_user_modules(st.session_state[SK.USERNAME])  # [] = unrestricted
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
            user_cos=get_user_companies(st.session_state[SK.USERNAME]), admin_mode=admin_mode)),
        ("tracking",       f"🏭 {t('Tracking')}",       lambda: _show_production_tracking_tab(
            user_cos=get_user_companies(st.session_state[SK.USERNAME]), admin_mode=admin_mode)),
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
        username=st.session_state[SK.USERNAME],
        admin_mode=admin_mode,
        user_factories=get_user_factories(st.session_state[SK.USERNAME]),
    )


@st.fragment
def _show_cmpt_tab(admin_mode: bool) -> None:
    from ui.cmpt_view import show_cmpt_tab
    show_cmpt_tab(username=st.session_state[SK.USERNAME], admin_mode=admin_mode)


@st.fragment
def _show_email_tab(admin_mode: bool) -> None:
    from ui.email_view import show_email_tab
    show_email_tab(username=st.session_state[SK.USERNAME], admin_mode=admin_mode)


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
    show_login()
