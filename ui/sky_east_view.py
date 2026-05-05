"""Sky East tab — public entry point and upload section (shell)."""
from __future__ import annotations
import streamlit as st
from ui.session_keys import SK
from ui.shared import ZIP_MIME, show_image_folder_expander
from ui.sky_east._shared import live_label
from ui.sky_east.processing import _run_sky_east_processing, _compute_se_missing_df
from ui.sky_east.items_view import _show_se_results, _show_se_missing_fields_section
from ui.sky_east.history import _show_se_history_section


# ---------------------------------------------------------------------------
# Upload section
# ---------------------------------------------------------------------------

def _show_se_upload_section():
    st.markdown("**Order Files** (Sky East Purchase Contract xlsx)")
    order_files = st.file_uploader(
        "Upload Sky East order file(s)",
        type=["xlsx", "xls", "xlsm"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="se_order_uploader",
    )
    if order_files:
        st.caption(f"{len(order_files)} file(s) selected")

    with st.expander("Reference files (optional -- Config SKU · Progress)"):
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

    show_image_folder_expander("se_images_dir", "se_images_dir_apply")

    se_mask = st.checkbox(
        "Mask prices",
        value=False,
        key="se_mask_prices",
        help="Replace FOB / cost / price columns with *** before download.",
    )

    st.divider()

    if not order_files:
        st.info("Upload one or more Sky East Purchase Contract Excel files to begin.")
        return

    if st.button("Process Sky East Files", type="primary",
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
        with st.expander("Processing log", expanded=False):
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
    st.subheader("Sky East Purchase Contracts")
    st.caption(
        "Upload one or more Sky East order Excel files. "
        "Files with the **same PC No.** are merged (quantities added). "
        "Changed size breakdowns are detected as amendments and logged to history."
    )

    _missing_df = _compute_se_missing_df()
    _missing_count = len(_missing_df)
    missing_label = (f"Missing Fields  {_missing_count}"
                     if _missing_count else "Missing Fields")

    se_tab_upload, se_tab_history, se_tab_missing = st.tabs(
        ["New Contracts", "Contract History", missing_label]
    )

    with se_tab_upload:
        _show_se_upload_section()

    with se_tab_history:
        _show_se_history_section()

    with se_tab_missing:
        _show_se_missing_fields_section(_missing_df)
