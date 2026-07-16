"""Admin panel: Application-wide settings."""
from __future__ import annotations

import os

import streamlit as st

from ui.i18n import t
from ui.session_keys import SK, COLOR_SOURCE_DB, COLOR_SOURCE_PROGRESS
from ui.stores import get_app_settings_store
from po_extractor.store.app_settings_store import (
    KEY_DEFAULT_COLOR_SOURCE,
    KEY_DEEPSEEK_API_KEY,
    KEY_EXTRACTION_METHOD,
    KEY_DEEPSEEK_MODEL,
    KEY_COLOR_AI_ENHANCE,
    KEY_MASK_USE_AI,
    KEY_CPRS_BASE_URL,
    KEY_CPRS_API_KEY,
    KEY_CPRS_SHOW_ADDRESS,
)
from po_extractor.utils.deepseek_client import chat_kwargs as _chat_kwargs

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SETTING_COLOR_SOURCE = KEY_DEFAULT_COLOR_SOURCE


@st.cache_data(ttl=1800, show_spinner=False)
def _live_deepseek_models(_key_fp: str) -> list[str]:
    """DeepSeek model ids from the live API, cached 30 min. Keyed on a
    fingerprint of the key (so a key change refetches) but reads the real key
    from the store — the raw key never enters the cache signature."""
    from po_extractor.parsers.deepseek_parser import list_models
    key = get_app_settings_store().get(KEY_DEEPSEEK_API_KEY, "")
    return list_models(key)

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
    st.markdown(f"### ⚙️ {t('Application Settings')}")
    st.caption(t(
        "Settings here apply to all users.  "
        "Individual users can still override per-session where allowed."
    ))

    store = get_app_settings_store()

    # ── Chinese color mapping default source ────────────────────────────────
    st.markdown("---")
    st.markdown(f"#### 🎨 {t('Chinese Color Mapping — Default Source')}")
    st.caption(t(
        "Controls the pre-selected option for the **Chinese color mapping source** "
        "radio on the Sky East tab.  New sessions start with this value; "
        "users can still change it within their session."
    ))

    current = store.get(_SETTING_COLOR_SOURCE, COLOR_SOURCE_DB)
    options  = list(_COLOR_SOURCE_OPTIONS.keys())
    idx      = options.index(current) if current in options else 0

    chosen_key = st.radio(
        t("Default source"),
        options,
        index=idx,
        format_func=lambda k: t(_COLOR_SOURCE_OPTIONS[k]),
        key="admin_default_color_src_radio",
    )
    st.info(t(_COLOR_SOURCE_HELP[chosen_key]), icon="ℹ️")

    if st.button(f"💾 {t('Save')}", key="admin_settings_save", type="primary"):
        store.set(
            _SETTING_COLOR_SOURCE,
            chosen_key,
            updated_by=st.session_state.get(SK.USERNAME, ""),
        )
        st.success(
            f"✅ {t('Default color source saved:')} **{t(_COLOR_SOURCE_OPTIONS[chosen_key])}**  \n"
            + t("New sessions will start with this selection.")
        )

    # ── DeepSeek AI Extraction ───────────────────────────────────────────────
    st.markdown("---")
    _show_deepseek_settings(store)

    # ── Colour Recognition — Local + AI Enhance ─────────────────────────────
    st.markdown("---")
    _show_color_ai_enhance_settings(store)

    # ── CPRS Knowledge Base ──────────────────────────────────────────────────
    st.markdown("---")
    _show_cprs_settings(store)

    # ── Fabric Master Database ───────────────────────────────────────────────
    st.markdown("---")
    _show_fabric_db_settings()


# ---------------------------------------------------------------------------
# CPRS Knowledge Base sub-section
# ---------------------------------------------------------------------------

def _show_cprs_settings(store) -> None:
    st.markdown(f"#### 🧭 {t('CPRS Knowledge Base')}")
    st.caption(t(
        "The Client PO Requirements System resolves carton marking, red-sticker "
        "codes, prepack ratio, pack-out, and MSRP/RFID for GIII buy plans. "
        "Configure its API here; leave blank to disable (buy plans still "
        "generate, with those fields left blank)."
    ))

    cur_url = store.get(KEY_CPRS_BASE_URL, "")
    cur_key = store.get(KEY_CPRS_API_KEY, "")
    cur_show = str(store.get(KEY_CPRS_SHOW_ADDRESS, "false")).lower() in ("true", "1", "yes")

    new_url = st.text_input(
        t("CPRS server address"), value=cur_url,
        placeholder="http://localhost:3100", key="admin_cprs_url",
        help=t("The CPRS API base URL, e.g. http://localhost:3100"),
    )
    new_key = st.text_input(
        t("CPRS API key"), value=cur_key, type="password",
        placeholder="x-api-key …", key="admin_cprs_key",
    )
    show_addr = st.checkbox(
        t("Show server address in the sidebar status"),
        value=cur_show, key="admin_cprs_show_addr",
        help=t("When off, the sidebar shows only Online/Offline + version; "
               "the host:port is hidden."),
    )

    col_test, col_save = st.columns([1, 1])
    with col_test:
        if st.button(f"🔌 {t('Test connection')}", key="admin_cprs_test",
                     disabled=not new_url.strip()):
            from po_extractor.utils.cprs_client import CprsClient
            ok, msg = CprsClient(new_url, new_key).health()
            (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")
    with col_save:
        if st.button(f"💾 {t('Save CPRS settings')}", key="admin_cprs_save",
                     type="primary"):
            user = st.session_state.get(SK.USERNAME, "")
            store.set(KEY_CPRS_BASE_URL, new_url.strip(), updated_by=user)
            store.set(KEY_CPRS_API_KEY, new_key.strip(), updated_by=user)
            store.set(KEY_CPRS_SHOW_ADDRESS,
                      "true" if show_addr else "false", updated_by=user)
            st.success(t("✅ CPRS settings saved."))


# ---------------------------------------------------------------------------
# DeepSeek AI Extraction sub-section
# ---------------------------------------------------------------------------

def _show_deepseek_settings(store) -> None:
    st.markdown(f"#### 🤖 {t('AI Extraction — DeepSeek')}")
    st.caption(t(
        "When enabled, PO PDFs are sent to the **DeepSeek API** for field extraction "
        "instead of (or alongside) the built-in regex parser.  "
        "Requires a DeepSeek API key from [platform.deepseek.com](https://platform.deepseek.com)."
    ))

    current_method = store.get(KEY_EXTRACTION_METHOD, "regex")
    current_key    = store.get(KEY_DEEPSEEK_API_KEY, "")
    current_model  = store.get(KEY_DEEPSEEK_MODEL, "deepseek-chat")

    method_options = {
        "regex":    "🔍 Regex (built-in, no API)",
        "deepseek": "🤖 DeepSeek AI (every file)",
        "auto":     "⚡ Auto — Regex first, AI only when low-confidence",
    }
    _method_keys = list(method_options.keys())
    chosen_method  = st.radio(
        t("Default extraction method"),
        _method_keys,
        index=_method_keys.index(current_method) if current_method in _method_keys else 0,
        format_func=lambda k: t(method_options[k]),
        key="admin_extraction_method",
        help=t("Auto is fastest for clean PDFs — it runs the instant built-in "
               "parser and only calls the (slower) AI for files that come back "
               "low-confidence or unparsed. Needs the API key below."),
    )

    col_key, col_model = st.columns([3, 1])
    with col_key:
        new_key = st.text_input(
            t("DeepSeek API Key"),
            value=current_key,
            type="password",
            placeholder="sk-...",
            key="admin_deepseek_key",
            disabled=(chosen_method == "regex"),
        )
    with col_model:
        # Model list is pulled live from the DeepSeek API (cached) so new
        # models (e.g. deepseek-v4-pro/flash) appear automatically, with a
        # static fallback and the currently-saved value always included.
        import hashlib as _hl
        from po_extractor.parsers.deepseek_parser import FALLBACK_MODELS
        _key_fp = _hl.md5((new_key or "").encode()).hexdigest()[:10] if new_key else ""
        live = _live_deepseek_models(_key_fp) if (chosen_method in ("deepseek", "auto") and new_key) else []
        model_options = list(dict.fromkeys(
            [m for m in live] + FALLBACK_MODELS
            + ([current_model] if current_model else [])
        ))
        new_model = st.selectbox(
            t("Model"),
            model_options,
            index=model_options.index(current_model) if current_model in model_options else 0,
            key="admin_deepseek_model",
            disabled=(chosen_method == "regex"),
            help=t("Fetched live from the DeepSeek API; falls back to a built-in list "
                   "if the API is unreachable."),
        )

    st.divider()
    st.markdown(f"**🔒 {t('AI-assisted price masking')}**")
    st.caption(t(
        "When masking prices, also ask DeepSeek to find prices from context "
        "(e.g. a whole-dollar FOB the pattern misses). AI findings are added to "
        "the built-in detection, never replace it. Uses the API key above; if "
        "it's unset or the call fails, masking falls back to the built-in rules."
    ))
    mask_ai = st.toggle(
        t("Use AI to detect prices when masking"),
        value=(store.get(KEY_MASK_USE_AI, "false") == "true"),
        key="admin_mask_use_ai",
    )

    col_test, col_save = st.columns([1, 1])
    with col_test:
        if st.button(f"🔌 {t('Test API key')}", key="admin_deepseek_test",
                     disabled=(chosen_method == "regex" or not new_key)):
            with st.spinner(f"{t('Testing…')}"):
                ok, msg = _test_deepseek(new_key, new_model)
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")
    with col_save:
        if st.button(f"💾 {t('Save AI settings')}", key="admin_deepseek_save", type="primary"):
            user = st.session_state.get(SK.USERNAME, "")
            store.set(KEY_EXTRACTION_METHOD, chosen_method, updated_by=user)
            store.set(KEY_DEEPSEEK_MODEL,    new_model,      updated_by=user)
            store.set(KEY_MASK_USE_AI, "true" if mask_ai else "false", updated_by=user)
            if new_key:
                store.set(KEY_DEEPSEEK_API_KEY, new_key, updated_by=user)
            st.success(t("✅ AI extraction settings saved."))


def _test_deepseek(api_key: str, model: str) -> tuple[bool, str]:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the word OK only."}],
            max_tokens=5,
            **_chat_kwargs(model),
        )
        reply = resp.choices[0].message.content or ""
        return True, f"API reachable — model={model}, reply='{reply.strip()}'"
    except Exception as exc:
        return False, str(exc)


# ---------------------------------------------------------------------------
# Colour Recognition — Local + AI Enhance sub-section
# ---------------------------------------------------------------------------

_COLOR_AI_MODE_OPTIONS: dict[str, str] = {
    "local":            "🔍 Local only (regex, no API)",
    "local_ai_enhance": "🤖 Local + AI Enhance",
}


def _show_color_ai_enhance_settings(store) -> None:
    st.markdown(f"#### 🎨 {t('Colour Recognition — Local + AI Enhance')}")
    st.caption(t(
        "Controls how Sky East order-file colours (e.g. a two-tone cell like "
        "\"(dark blue)(white)\") are matched against 大货进度表 / the internal "
        "colour DB. **Local only** relies purely on regex detection and never "
        "makes a network call. **Local + AI Enhance** falls back to the "
        "DeepSeek API, but *only* when a colour has already failed to resolve "
        "locally — it is never called for anything else (dates, quantities, "
        "other fields), to avoid spending API tokens unnecessarily. "
        "Uses the same DeepSeek API key/model configured above."
    ))

    current_mode = store.get(KEY_COLOR_AI_ENHANCE, "local")
    chosen_mode  = st.radio(
        t("Colour recognition mode"),
        list(_COLOR_AI_MODE_OPTIONS.keys()),
        index=0 if current_mode == "local" else 1,
        format_func=lambda k: t(_COLOR_AI_MODE_OPTIONS[k]),
        key="admin_color_ai_enhance_mode",
    )

    has_key = bool(store.get(KEY_DEEPSEEK_API_KEY, ""))
    if chosen_mode == "local_ai_enhance" and not has_key:
        st.warning(
            t("⚠️ No DeepSeek API key configured above — AI Enhance will have "
              "no effect until one is saved."),
            icon="⚠️",
        )

    if st.button(f"💾 {t('Save colour recognition mode')}", key="admin_color_ai_enhance_save",
                 type="primary"):
        store.set(
            KEY_COLOR_AI_ENHANCE, chosen_mode,
            updated_by=st.session_state.get(SK.USERNAME, ""),
        )
        st.success(f"✅ {t('Colour recognition mode saved:')} **{t(_COLOR_AI_MODE_OPTIONS[chosen_mode])}**")


# ---------------------------------------------------------------------------
# Fabric Master DB sub-section
# ---------------------------------------------------------------------------

def _show_fabric_db_settings() -> None:
    from po_extractor.config import (
        get_fabric_db_path, save_fabric_db_path, DB_PATH,
    )
    from po_extractor.store.fabric_master_store import FabricMasterStore
    from fabric_master_client import FabricMasterClient

    st.markdown(f"#### 🗄 {t('Fabric Master Database')}")
    st.caption(t(
        "The fabric master lives in its **own dedicated SQLite file** so that "
        "other applications can share the same data.  Point any app's "
        "`FabricMasterStore` (or copy `fabric_master_client.py`) at the path "
        "below to get read access."
    ))

    current_path = get_fabric_db_path()

    # ── Current status ───────────────────────────────────────────────────────
    ok, status_msg = FabricMasterClient.test_connection(current_path)
    if ok:
        st.success(f"✅ {t('Connected —')} {status_msg}  \n`{current_path}`")
    else:
        st.warning(f"⚠️ {t('Cannot connect:')} {status_msg}  \n`{current_path}`")

    env_override = os.environ.get("FABRIC_DB_PATH", "").strip()
    if env_override:
        st.info(
            t("ℹ️ Path is overridden by the `FABRIC_DB_PATH` environment variable.  "
              "Clear the env var to use the path configured below."),
            icon="🔒",
        )

    # ── Path editor ──────────────────────────────────────────────────────────
    with st.expander(f"✏️ {t('Change fabric master DB path')}", expanded=not ok):
        st.caption(t(
            "Enter an absolute path to the `fabric_master.db` file.  "
            "All apps sharing this file must have read access to the same location "
            "(e.g. a mapped network drive or shared folder)."
        ))
        new_path = st.text_input(
            t("Fabric master DB path"),
            value=current_path,
            key="admin_fabric_db_path_input",
            placeholder=r"C:\Shared\fabric_master.db",
            disabled=bool(env_override),
        )

        col_test, col_save = st.columns([1, 1])
        with col_test:
            if st.button(f"🔌 {t('Test connection')}", key="admin_fabric_test_btn"):
                test_ok, test_msg = FabricMasterClient.test_connection(new_path)
                if test_ok:
                    st.success(f"✅ {test_msg}")
                else:
                    st.error(f"❌ {test_msg}")

        with col_save:
            if st.button(
                f"💾 {t('Save path')}",
                key="admin_fabric_save_path_btn",
                type="primary",
                disabled=bool(env_override),
            ):
                save_fabric_db_path(new_path.strip())
                st.success(t("✅ Path saved to `fabric_config.json`.  Reload the page to apply."))
                st.rerun()

    # ── Migration ────────────────────────────────────────────────────────────
    with st.expander(f"📦 {t('Migrate existing fabric data from main app DB')}"):
        st.caption(t(
            "If you previously used this app before the centralised fabric DB "
            "was introduced, your fabric data is still in `po_history.db`.  "
            "Click below to copy it into the dedicated `fabric_master.db`."
        ))

        src_count = _count_fabric_in_db(DB_PATH)
        dst_count = FabricMasterStore(current_path).count() if ok else 0

        col1, col2 = st.columns(2)
        col1.metric(t("Records in po_history.db"), src_count)
        col2.metric(t("Records in fabric_master.db"), dst_count)

        if src_count == 0:
            st.info(t("No fabric records found in `po_history.db` — nothing to migrate."))
        else:
            if st.button(
                f"📦 {t('Migrate')} {src_count} {t('records → fabric_master.db')}",
                key="admin_fabric_migrate_btn",
                type="primary",
            ):
                with st.spinner(f"{t('Migrating…')}"):
                    result = FabricMasterStore.migrate_from_db(DB_PATH, current_path)
                st.success(
                    f"✅ {t('Migration complete.')}  {result['message']}  \n"
                    + f"{t('fabric_master.db now has')} **{FabricMasterStore(current_path).count()}** {t('records.')}"
                )

    # ── Integration guide ────────────────────────────────────────────────────
    with st.expander(f"📋 {t('How other apps connect to this database')}"):
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
