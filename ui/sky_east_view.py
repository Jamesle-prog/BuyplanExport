"""Sky East tab — public entry point and upload section (shell)."""
from __future__ import annotations
import streamlit as st
from ui.i18n import t
from ui.session_keys import SK, COLOR_SOURCE_DB, COLOR_SOURCE_PROGRESS
from ui.shared import lazy_sections, ZIP_MIME, show_image_folder_expander, show_processing_log
from ui.sky_east._shared import live_label, show_color_source_radio
from ui.sky_east.processing import _run_sky_east_processing, _compute_se_missing_df
from ui.sky_east.items_view import (
    _show_se_results, _show_se_missing_fields_section, _show_return_label_conflicts,
    _show_new_brand_shipping_sample_prompt,
)
from ui.sky_east.history import _show_se_history_section
from ui.sky_east.reports_tab import PIN_BUYPLAN, _show_se_reports_tab

# Color source radio is defined in sky_east._shared.show_color_source_radio
# and shared with the Buy Plan section in the history tab.


# How a re-uploaded contract is written. Merge only ever adds and updates, so
# a style withdrawn from the order — or a row that duplicated one already on
# file — survives every later upload; replace makes the DB match the file.
SE_SAVE_MERGE = "merge"
SE_SAVE_REPLACE = "replace"

_SE_SAVE_MODES = {
    SE_SAVE_MERGE:   "🔀 Update / add only",
    SE_SAVE_REPLACE: "♻️ Replace the whole contract",
}

_SE_SAVE_MODE_HELP = {
    SE_SAVE_MERGE: (
        "New items are added and changed ones updated. Nothing is ever "
        "removed, so items on file that this file doesn't list are kept."
    ),
    SE_SAVE_REPLACE: (
        "The uploaded file becomes the complete contract: items it doesn't "
        "list are archived and removed from the active order."
    ),
}


# ---------------------------------------------------------------------------
# Upload section
# ---------------------------------------------------------------------------


def _brands_awaiting_requirement() -> list[str]:
    """Every Sky East brand on file with no 船样要求 text yet.

    Union of what the last upload flagged and what the store says is still
    blank: the upload list alone misses brands that were registered before the
    requirement became compulsory, and the store alone would forget a brand
    the current upload has only just introduced.
    """
    pending = list(st.session_state.get(SK.SE_NEW_BRAND_PENDING) or [])
    try:
        from auth.companies import COMPANY_SKY_EAST
        from ui.stores import get_boat_sample_store, get_sky_east_store
        items = get_sky_east_store().list_items()
        brands = sorted({str(b).strip() for b in items.get("brand", [])
                         if str(b or "").strip()}) if not items.empty else []
        blank = get_boat_sample_store().brands_missing_requirement(
            COMPANY_SKY_EAST, brands) if brands else []
    except Exception:
        blank = []          # never let a lookup failure hide the upload's own list
    seen, out = set(), []
    for b in list(pending) + list(blank):
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def _show_se_upload_section():
    st.markdown(f"**{t('Order Files')}** (Sky East Purchase Contract xlsx)")
    order_files = st.file_uploader(
        t("Upload Sky East order file(s)"),
        type=["xlsx", "xls", "xlsm"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="se_order_uploader",
    )
    if order_files:
        st.caption(f"{len(order_files)} " + t("file(s) selected"))

    with st.expander(f"{t('Reference files')} (optional — Config SKU · Progress)", expanded=True):
        ref_l, ref_r = st.columns(2)
        with ref_l:
            ean_file = st.file_uploader(
                t("Config SKU file (Zalando PO report xlsx)"),
                type=["xlsx", "xls"],
                key="se_ean_uploader",
                help=(
                    t("**Lookup keys (all four must match):**\n"
                    "- Purchase Order Number\n"
                    "- Color name\n"
                    "- Brand\n"
                    "- Style No.\n\n"
                    "**Returns:** Config SKU\n\n"
                    "Conflicting values for the same combination are flagged in the log.")
                ),
            )
            st.caption(
                "💡 " + t("Upload fabric mapping independently in the **📐 Reference Data** tab.")
            )
        with ref_r:
            progress_file = st.file_uploader(
                t("HHN contract No. file"),
                type=["xlsx", "xls"],
                key="se_progress_uploader",
                help=(
                    t("**Sheet:** first sheet with '2026' or 'Zalando' in its name\n\n"
                    "**Lookup keys:**\n"
                    "- Col 5: 款式 (Style No.)\n"
                    "- Col 7: 颜色 (Color)\n\n"
                    "**Returns:**\n"
                    "- Col 2: 合同号 (HHN Contract No.)\n"
                    "- Col 4: Image (DISPIMG)\n"
                    "- Col 10: PO离厂日期 (Ex-Fty Date)\n\n"
                    "Column positions are auto-detected by header name.")
                ),
            )
            st.caption(t(
                "💡 One-off for this run. To reuse the 大货进度表 across runs, save it "
                "in the **📐 Reference Data → HHN Contract Progress** tab."
            ))

    # ── Chinese color mapping source ──────────────────────────────────────────
    show_color_source_radio("se_color_src_radio")
    st.caption(t(
        "↑ Sets the default colour source used when you **generate the Buy Plan** "
        "(📦 Generate / Export tab). It doesn't change this Process step."
    ))

    show_image_folder_expander("se_images_dir", "se_images_dir_apply")

    se_mask = st.checkbox(
        t("Mask prices"),
        value=False,
        key="se_mask_prices",
        help=t("Replace FOB / cost / price columns with *** before download."),
    )

    # ── How an already-imported contract is written ──────────────────────────
    st.markdown(f"**{t('If the contract is already in the system')}**")
    # captions= puts each explanation under its own option, so the two are
    # readable side by side before choosing — the difference is destructive,
    # so it shouldn't take switching the radio to find out what it does.
    save_mode = st.radio(
        t("Save mode"),
        [SE_SAVE_MERGE, SE_SAVE_REPLACE],
        format_func=lambda m: t(_SE_SAVE_MODES[m]),
        captions=[t(_SE_SAVE_MODE_HELP[m])
                  for m in (SE_SAVE_MERGE, SE_SAVE_REPLACE)],
        horizontal=True,
        label_visibility="collapsed",
        key=SK.SE_SAVE_MODE,
    )
    replace_confirmed = False
    if save_mode == SE_SAVE_REPLACE:
        st.warning(t(
            "⚠️ Replace removes items this file doesn't list — use it when the "
            "upload is the complete, current contract, not a partial revision. "
            "Removed items are archived and stay visible in item history. "
            "Fabric No. and 合同号 entered in the app are kept for items the "
            "file still lists."
        ))
        replace_confirmed = st.checkbox(
            t("I understand — replace the contract and remove the items this "
              "file doesn't list"),
            key=SK.SE_REPLACE_CONFIRM,
        )
    else:
        # Don't let a tick made earlier survive a switch back to replace: the
        # confirmation has to be given for the run it applies to.
        st.session_state.pop(SK.SE_REPLACE_CONFIRM, None)

    st.divider()

    if not order_files:
        st.info(t("Upload one or more Sky East Purchase Contract Excel files to begin."))
        return

    needs_confirm = save_mode == SE_SAVE_REPLACE and not replace_confirmed
    if needs_confirm:
        st.caption("☝️ " + t("Tick the box above to enable processing in "
                             "replace mode."))

    if st.button(t("Process Sky East Files"), type="primary",
                 width="stretch", key="se_run",
                 disabled=needs_confirm):
        st.session_state[SK.SE_RESULTS] = None
        st.session_state[SK.SE_LOG] = []
        st.session_state[SK.SE_CONTRACTS] = None
        st.session_state[SK.SE_IMAGE_CACHE] = {}
        # New upload run → freshly extracted photos may supersede cached ones
        st.session_state.pop(SK.SE_PHOTO_CACHE, None)
        st.session_state[SK.SE_MASKED_ZIP] = None
        _run_sky_east_processing(order_files, ean_file, progress_file,
                                 mask_prices=se_mask, save_mode=save_mode)
        # One tick authorises one run — the next upload has to confirm again,
        # or a replace made now would silently repeat on the next file.
        st.session_state.pop(SK.SE_REPLACE_CONFIRM, None)
        st.rerun()

    if st.session_state[SK.SE_LOG]:
        show_processing_log(st.session_state[SK.SE_LOG])

    _rl_pending = st.session_state.get(SK.SE_RL_PENDING)
    if _rl_pending:
        _show_return_label_conflicts(_rl_pending)

    # Any brand with a blank 船样要求 is asked about, every time this screen is
    # drawn -- not only the ones a fresh upload happened to introduce. The
    # requirement is compulsory, so a brand that slipped through (or was
    # deferred with "Remind me later") has to keep coming back rather than
    # sitting blank until someone notices an empty column in a buy plan.
    _show_new_brand_shipping_sample_prompt(_brands_awaiting_requirement())

    if st.session_state.get(SK.SE_MASKED_ZIP):
        st.download_button(
            t("Download Masked Files (.zip)"),
            data=st.session_state[SK.SE_MASKED_ZIP],
            file_name="sky_east_masked.zip",
            mime=ZIP_MIME,
            width="stretch",
            key="se_masked_dl",
        )

    if st.session_state[SK.SE_RESULTS]:
        _n_saved = len(st.session_state[SK.SE_RESULTS])
        st.success(
            f"✅ {t('Saved')} {_n_saved} PC No.(s). " + t(
                "**Next step →** open the **📦 Generate / Export** tab → "
                "**Buy Plan + 核料** to generate outputs "
                "(or **Contract History** to review saved data)."
            ),
            icon="✅",
        )
        _show_se_results(st.session_state[SK.SE_RESULTS], st.session_state[SK.SE_IMAGE_CACHE])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def show_sky_east_tab(restrict_to_buyplan: bool = False) -> None:
    """Sky East purchase-contract upload, merge, amendment review, and history.

    ``restrict_to_buyplan=True`` renders a narrowed view for the "Sky East —
    Buy Plan only" user role: just Upload + Generate/Export pinned to Buy
    Plan mode. Contract History and Missing Fields stay hidden.
    """
    st.subheader(t("Sky East Purchase Contracts"))
    st.caption(t(
        "Upload one or more Sky East order Excel files. "
        "Files with the **same PC No.** are merged (quantities added). "
        "Changed size breakdowns are detected as amendments and logged to history."
    ))

    if restrict_to_buyplan:
        lazy_sections([
            (t("New Contracts"),            _show_se_upload_section),
            (f"📦 {t('Generate / Export')}",
             lambda: _show_se_reports_tab(pin_mode=PIN_BUYPLAN)),
        ], key="se_bp_section_nav")
        return

    _missing_df = _compute_se_missing_df()
    _missing_count = len(_missing_df)
    _mf = t("Missing Fields")
    missing_label = (f"{_mf}  {_missing_count}" if _missing_count else _mf)

    # "Generate / Export" sits right after "New Contracts" so the natural flow
    # is Upload → Generate; it's the primary output step and shouldn't be buried
    # behind Contract History.
    lazy_sections([
        (t("New Contracts"),               _show_se_upload_section),
        (f"📦 {t('Generate / Export')}",    _show_se_reports_tab),
        (t("Contract History"),            _show_se_history_section),
        (missing_label,
         lambda: _show_se_missing_fields_section(_missing_df)),
    ], key="se_section_nav")
