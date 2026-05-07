"""Sky East tab — public entry point and upload section (shell)."""
from __future__ import annotations
import streamlit as st
from ui.i18n import t
from ui.session_keys import SK, COLOR_SOURCE_DB, COLOR_SOURCE_PROGRESS
from ui.shared import ZIP_MIME, show_image_folder_expander
from ui.sky_east._shared import live_label
from ui.sky_east.processing import _run_sky_east_processing, _compute_se_missing_df
from ui.sky_east.items_view import _show_se_results, _show_se_missing_fields_section
from ui.sky_east.history import _show_se_history_section

# Stable ordering for radio options (translation-independent).
_COLOR_SOURCE_KEYS = [COLOR_SOURCE_DB, COLOR_SOURCE_PROGRESS]

# English keys used for t() lookup; "大货进度表 (HHN Contract File)" is already
# bilingual so we keep it verbatim.
_COLOR_SOURCE_EN: dict[str, str] = {
    COLOR_SOURCE_DB:       "Internal Database",
    COLOR_SOURCE_PROGRESS: "大货进度表 (HHN Contract File)",
}

# Per-option lookup-key explainer shown beneath the radio (intentionally bilingual).
_COLOR_SOURCE_CAPTIONS: dict[str, str] = {
    COLOR_SOURCE_DB: (
        "🔑 **Lookup keys:** Client · Brand · English color name  "
        "→ **Returns:** 中文颜色, 中文颜色代码, 主标颜色  "
        "*(source: 🎨 Colors tab — color_translation table)*"
    ),
    COLOR_SOURCE_PROGRESS: (
        "🔑 **Lookup keys (priority order):**  \n"
        "1. PC No (所在PO / 客人PC No) · 款式 · 颜色  \n"
        "2. PO# · 款式 · 颜色  \n"
        "3. 款式 · 颜色  \n"
        "4. PC No · 款式 · 颜色代码  \n"
        "5. 款式 · 颜色代码  \n"
        "6. PC No · 款式  \n"
        "7. 款式 only (last resort)  \n"
        "→ **Returns:** 中文颜色, 中文颜色代码, 主标颜色  "
        "*(source: HHN Contract No. file — 大货进度表)*"
    ),
}


def _show_color_source_radio() -> None:
    """Render the Chinese-colour-source radio + per-option lookup-key caption."""
    cur = st.session_state.get(SK.SE_COLOR_SOURCE, COLOR_SOURCE_DB)
    # Build translated labels at render time so they reflect the active language.
    labels = [t(_COLOR_SOURCE_EN[k]) for k in _COLOR_SOURCE_KEYS]
    chosen = st.radio(
        t("Chinese color mapping source") + " (中文颜色 / 中文颜色代码)",
        labels,
        index=_COLOR_SOURCE_KEYS.index(cur) if cur in _COLOR_SOURCE_KEYS else 0,
        horizontal=True,
        key="se_color_src_radio",
    )
    new = _COLOR_SOURCE_KEYS[labels.index(chosen)]
    if new != cur:
        st.session_state[SK.SE_COLOR_SOURCE] = new
    st.caption(_COLOR_SOURCE_CAPTIONS[new])


# ---------------------------------------------------------------------------
# Upload section
# ---------------------------------------------------------------------------

def _show_se_upload_section():
    st.markdown(f"**{t('Order Files')}** (Sky East Purchase Contract xlsx)")
    order_files = st.file_uploader(
        "Upload Sky East order file(s)",
        type=["xlsx", "xls", "xlsm"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="se_order_uploader",
    )
    if order_files:
        st.caption(f"{len(order_files)} file(s) selected")

    with st.expander(f"{t('Reference files')} (optional — Config SKU · Progress)"):
        ref_l, ref_r = st.columns(2)
        with ref_l:
            ean_file = st.file_uploader(
                "Config SKU file (Zalando PO report xlsx)",
                type=["xlsx", "xls"],
                key="se_ean_uploader",
                help=(
                    "**Lookup keys (all four must match):**\n"
                    "- Purchase Order Number\n"
                    "- Color name\n"
                    "- Brand\n"
                    "- Style No.\n\n"
                    "**Returns:** Config SKU\n\n"
                    "Conflicting values for the same combination are flagged in the log."
                ),
            )
            st.caption(
                "💡 Upload fabric mapping independently in **Contract History → "
                "🧵 Fabric Mapping**."
            )
        with ref_r:
            progress_file = st.file_uploader(
                "HHN contract No. file",
                type=["xlsx", "xls"],
                key="se_progress_uploader",
                help=(
                    "**Sheet:** first sheet with '2026' or 'Zalando' in its name\n\n"
                    "**Lookup keys:**\n"
                    "- Col 5: 款式 (Style No.)\n"
                    "- Col 7: 颜色 (Color)\n\n"
                    "**Returns:**\n"
                    "- Col 2: 合同号 (HHN Contract No.)\n"
                    "- Col 4: Image (DISPIMG)\n"
                    "- Col 10: PO离厂日期 (Ex-Fty Date)\n\n"
                    "Column positions are auto-detected by header name."
                ),
            )

    # ── Chinese color mapping source ──────────────────────────────────────────
    _show_color_source_radio()

    show_image_folder_expander("se_images_dir", "se_images_dir_apply")

    se_mask = st.checkbox(
        t("Mask prices"),
        value=False,
        key="se_mask_prices",
        help="Replace FOB / cost / price columns with *** before download.",
    )

    st.divider()

    if not order_files:
        st.info(t("Upload one or more Sky East Purchase Contract Excel files to begin."))
        return

    if st.button(t("Process Sky East Files"), type="primary",
                 use_container_width=True, key="se_run"):
        st.session_state.se_results = None
        st.session_state.se_log = []
        st.session_state.se_contracts = None
        st.session_state.se_image_cache = {}
        st.session_state.se_masked_zip = None
        _run_sky_east_processing(order_files, ean_file, progress_file,
                                 mask_prices=se_mask)
        st.rerun()

    if st.session_state.se_log:
        with st.expander(t("Processing log"), expanded=False):
            for line in st.session_state.se_log:
                st.markdown(line, unsafe_allow_html=True)

    if st.session_state.get(SK.SE_MASKED_ZIP):
        st.download_button(
            "Download Masked Files (.zip)",
            data=st.session_state.se_masked_zip,
            file_name="sky_east_masked.zip",
            mime=ZIP_MIME,
            use_container_width=True,
            key="se_masked_dl",
        )

    if st.session_state.se_results:
        _show_se_results(st.session_state.se_results, st.session_state.se_image_cache)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_sky_east_tab() -> None:
    """Sky East purchase-contract upload, merge, amendment review, and history."""
    st.subheader(t("Sky East Purchase Contracts"))
    st.caption(t(
        "Upload one or more Sky East order Excel files. "
        "Files with the **same PC No.** are merged (quantities added). "
        "Changed size breakdowns are detected as amendments and logged to history."
    ))

    _missing_df = _compute_se_missing_df()
    _missing_count = len(_missing_df)
    _mf = t("Missing Fields")
    missing_label = (f"{_mf}  {_missing_count}" if _missing_count else _mf)

    se_tab_upload, se_tab_history, se_tab_missing = st.tabs(
        [t("New Contracts"), t("Contract History"), missing_label]
    )

    with se_tab_upload:
        _show_se_upload_section()

    with se_tab_history:
        _show_se_history_section()

    with se_tab_missing:
        _show_se_missing_fields_section(_missing_df)
