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
    SE_BP_DIAGS      = "se_bp_diags"    # [sky_east ...] warnings captured during generation
    SE_BP_NOPHOTO    = "se_bp_nophoto"  # styles with no photo in the generated buy plan

    # ── Sky East — color mapping source preference ────────────────────────────
    SE_COLOR_SOURCE  = "se_color_source"   # value: COLOR_SOURCE_DB | COLOR_SOURCE_PROGRESS

    # ── Production Tracking ───────────────────────────────────────────────────
    # All "selected" keys store the INTEGER record id (never a concatenated
    # string).  See docs/development_plan_production_tracking.md §1.5
    # "Record identity contract".
    PT_SELECTED_EDIT  = "pt_selected_edit"   # int — id of record selected in Edit
    PT_SELECTED_PLAN  = "pt_selected_plan"   # int — id of record selected in Plan
    PT_PLAN_OVERRIDE  = "pt_plan_override"   # dict[stage, int] — what-if day overrides
    PT_DELETE_CONFIRM = "pt_delete_confirm"  # bool — delete confirmation shown
    PT_DELETE_FLASH   = "pt_delete_flash"    # str — one-shot success msg after delete
    PT_ACTIVE_TAB     = "pt_active_tab"      # int — active sub-tab index (0=Dashboard)
    PT_ADD_CLIENT     = "pt_add_client"      # str — Add New tab's client filter

    # ── GIII fax/portal extraction sections (MSG / KL / TK EU / InforNexus) ──
    # *_SIG holds the uploader file-set signature the results were built from
    # (ui.giii._shared.files_signature) — mismatch = stale results, dropped.
    GIII_MSG_RESULTS   = "msg_results"       # list[dict] — parsed MSG POs
    GIII_MSG_SIG       = "msg_results_sig"
    GIII_KL_RESULTS    = "kl_results"        # list[dict] — parsed KL POs
    GIII_KL_SIG        = "kl_results_sig"
    GIII_TKEU_RESULTS  = "tk_eu_results"     # list[dict] — parsed TK EU POs
    GIII_TKEU_SIG      = "tk_eu_results_sig"
    GIII_IN_RESULTS    = "in_results"        # list[dict] — parsed InforNexus POs
    GIII_IN_SIG        = "in_results_sig"
    GIII_IN_KL_RESULTS = "in_kl_results"     # list[dict] — KL fax POs (comparison set)
    GIII_IN_KL_SIG     = "in_kl_results_sig"

    # GIII master-table persisted download (ui/giii/results.py)
    GIII_MASTER_DL_BYTES = "master_dl_bytes"
    GIII_MASTER_DL_FNAME = "master_dl_fname"


# Allowed values for ``SK.SE_COLOR_SOURCE`` — controls where the buy-plan
# Chinese colour mapping (中文颜色 / 中文颜色代码 / 主标颜色) is loaded from.
COLOR_SOURCE_DB       = "db"        # 🎨 Colors tab — color_translation table
COLOR_SOURCE_PROGRESS = "progress"  # 大货进度表 — HHN Contract No. file
