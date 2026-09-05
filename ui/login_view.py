"""Sign-in page and account forms — extracted from app.py.

Everything a visitor sees before they are logged in lives here: the
"Threadline Login" split-screen page (hero panel + form), the sign-in
handling with its lockout and audit log, and the change-password form the
signed-in sidebar embeds.  app.py keeps only the router.

Why the page's CSS and hero markup are module constants rather than built
per call: they are pure strings, and the login page is re-rendered on
every keystroke-free rerun; there is nothing to recompute.
"""
from __future__ import annotations

import streamlit as st

from auth import login_throttle as _throttle
from auth.users import change_password, verify_password
from po_extractor.config import APP_NAME, APP_TAGLINE
from ui.i18n import t
from ui.session_keys import SK


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


def show_login(app_version: str) -> None:
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
            source = _client_ip()
            wait = _throttle.wait_seconds(uname_key, source)
            if wait:
                _record_login(username, "locked", f"locked {wait}s")
                st.error(f"{t('Too many failed attempts. Try again in')} {wait} s.")
            elif verify_password(username, password):
                _throttle.record_success(uname_key)
                _record_login(username, "success")
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.results = None
                st.session_state.parse_log = []
                st.rerun()
            else:
                _throttle.record_failure(uname_key)
                _throttle.record_global_failure(source)
                _record_login(username, "failed", "wrong username or password")
                st.error(t("Incorrect username or password."))

        st.markdown(
            f"<div class='tl-foot'>🔒 {t('Authorized users only')} · "
            f"<b>{APP_NAME}</b> v{app_version}</div>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Change password — sidebar form
# ---------------------------------------------------------------------------
def show_change_password_sidebar() -> None:
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
