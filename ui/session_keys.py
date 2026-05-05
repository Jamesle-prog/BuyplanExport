"""Centralised session-state key constants.

Import ``SK`` wherever ``st.session_state`` is accessed so that key strings
are defined in exactly one place and never silently diverge across modules.
"""


class SK:
    """Namespace for all Streamlit session-state key strings."""

    # ── Auth ─────────────────────────────────────────────────────────────────
    LOGGED_IN        = "logged_in"
    USERNAME         = "username"
    SHOW_CHANGE_PW   = "show_change_pw"
    SHOW_ADMIN       = "show_admin"
    UI_LANG          = "ui_lang"

    # ── GIII ─────────────────────────────────────────────────────────────────
    RESULTS          = "results"
    PARSE_LOG        = "parse_log"
    HISTORY_RESULTS  = "history_results"
    HISTORY_BP_BYTES = "history_bp_bytes"
    GIII_MAPPING     = "giii_mapping_result"

    # ── Sky East — processing ─────────────────────────────────────────────────
    SE_RESULTS       = "se_results"
    SE_LOG           = "se_log"
    SE_CONTRACTS     = "se_contracts"
    SE_IMAGE_CACHE   = "se_image_cache"
    SE_FABRIC_LOOKUP = "se_fabric_lookup"
    SE_PROGRESS_LKUP = "se_progress_lookup"
    SE_MASKED_ZIP    = "se_masked_zip"
    SE_IMAGES_DIR    = "se_images_dir"

    # ── Sky East — item download ───────────────────────────────────────────────
    SE_DL_BYTES      = "se_dl_bytes"
    SE_DL_FNAME      = "se_dl_fname"
    SE_DL_MIME       = "se_dl_mime"

    # ── Sky East — wash label ─────────────────────────────────────────────────
    SE_WL_BYTES      = "se_wl_bytes"
    SE_WL_FNAME      = "se_wl_fname"
    SE_WL_PENDING    = "se_wl_pending"   # pending validation context dict

    # ── Sky East — buy plan ───────────────────────────────────────────────────
    SE_BP_BYTES      = "se_bp_bytes"
    SE_BP_NAME       = "se_bp_name"
    SE_NK_BYTES      = "se_nk_bytes"
    SE_NK_COUNT      = "se_nk_count"
    SE_NK_REASON     = "se_nk_reason"   # human-readable reason when 核料 is empty
    SE_BP_CMP        = "se_bp_cmp"
