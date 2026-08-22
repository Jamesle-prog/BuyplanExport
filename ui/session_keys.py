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
    SE_SAVE_MODE = "se_save_mode"   # "merge" | "replace" — how a re-uploaded contract is written
    SE_REPLACE_CONFIRM = "se_replace_confirm"   # bool — one tick authorises one replace run
    SE_IMAGES_DIR    = "se_images_dir"
    SE_RL_PENDING    = "se_return_label_pending"   # Return Label conflicts awaiting confirmation
    SE_NEW_BRAND_PENDING = "se_new_brand_pending"   # brand names awaiting a 船样要求 entry

    SE_PHOTO_CACHE   = "se_photo_cache"    # {"key": (folder, styles), "map": style→[front,back]} per session
    SE_OUTPUT_DIR    = "se_output_dir"     # optional folder to save generated buy plan / 核料 into

    # ── Fabric DB ─────────────────────────────────────────────────────────────
    FABRIC_DB_FLASH  = "fabric_db_flash"   # import/delete outcome shown after the post-action rerun

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
    PT_SELECTED_EDIT  = "pt_selected_edit"   # int — id of record selected in Advanced editor
    PT_DELETE_CONFIRM = "pt_delete_confirm"  # bool — delete confirmation shown
    PT_DELETE_FLASH   = "pt_delete_flash"    # str — one-shot success msg after delete
    PT_ACTIVE_TAB     = "pt_active_tab"      # int — active sub-tab index (0=Tracking Grid)
    PT_ADD_CLIENT     = "pt_add_client"      # str — Add tab's client filter
    PT_GRID_MODE      = "pt_grid_mode"       # str — grid date mode: planned | actual
    PT_GRID_SEARCH    = "pt_grid_search"     # str — grid PO/style search box

    # ── Email (📧 inbox review + notifications) ───────────────────────────────
    EMAIL_ACTIVE_TAB   = "email_active_tab"    # int — active sub-tab index
    EMAIL_FETCH_FLASH  = "email_fetch_flash"   # str — one-shot result of the last check
    EMAIL_LAST_FETCH   = "email_last_fetch"    # str — timestamp of last mailbox check
    EMAIL_AUTO_CHECKED = "email_auto_checked"  # bool — auto-check already ran this session

    # ── GIII — upload auto-detection cache ────────────────────────────────────
    GIII_DETECTIONS   = "giii_detections"     # list[DetectionResult] for current upload set
    GIII_DETECT_SIG   = "giii_detect_sig"     # files_signature the detections were built from
    GIII_OTHER_GROUPS = "giii_other_groups"   # dict[class -> UploadedFiles] for Other PO types
    GIII_OTHER_SIG    = "giii_other_sig"      # files_signature the groups were built from

    # ── Summary — combined All Orders sub-tab ─────────────────────────────────
    SUM_ALL_CLIENTS   = "sum_all_clients"    # list[str] — company filter multiselect
    SUM_ALL_SEARCH    = "sum_all_search"     # str — PO/style/color search box
    SUM_ALL_COLS      = "sum_all_cols"       # list[str] — standard-column picker

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

    FM_DUP_RESULTS  = "fm_tab_dup_results"  # duplicate fabric-combo scan results

    # ── Cutting Plan (✂️ 裁剪计划) ─────────────────────────────────────────────
    CP_PARSED       = "cp_parsed"        # list[dict] — parsed uploads awaiting save
    CP_PARSE_SIG    = "cp_parse_sig"     # uploader signature the parses were built from
    CP_FLASH        = "cp_flash"         # one-shot (kind, message) after a save/delete
    CP_EDIT_ID      = "cp_edit_id"       # plan id whose links are being edited
    CP_STD_BYTES    = "cp_std_bytes"     # generated standard cut plan bytes
    CP_STD_FNAME    = "cp_std_fname"
    CP_STD_CN_CONFLICTS = "cp_std_cn_conflicts"  # plan-vs-PO colour disagreements
    CP_SECTION_NAV  = "cp_section_nav"   # selected section of the cutting plan tab

    # ── Settlement (💰 结算统计表) ────────────────────────────────────────────
    ST_PARSED    = "st_parsed"      # dict — parsed upload awaiting import
    ST_PARSE_SIG = "st_parse_sig"   # uploader signature the parse was built from
    ST_FLASH     = "st_flash"       # one-shot (kind, message) after an import
    ST_NAV       = "st_nav"         # selected section of the settlement tab

    # ── Fabric Condition (📏 面料情况) ────────────────────────────────────────
    FC_PARSED    = "fc_parsed"      # dict — parsed upload awaiting import
    FC_PARSE_SIG = "fc_parse_sig"   # uploader signature the parse was built from
    FC_FLASH     = "fc_flash"       # one-shot (kind, message) after an import
    FC_NAV       = "fc_nav"         # selected section of the fabric condition tab

    # ── Widget / state keys promoted from string literals (v2.134.0) ─────────
    # Each was used as a raw literal somewhere in ui/; they are widget keys
    # as often as plain state, so the same constant is passed as key= too.
    # CMPT
    CMPT_DETAIL_SEL   = "cmpt_detail_sel"
    CMPT_NEW_LINES_DF = "cmpt_new_lines_df"
    CMPT_NEW_NO       = "cmpt_new_no"
    # Colors
    CT_AUDIT_CONFIRM = "_ct_audit_confirm"
    CT_DATA_NONCE    = "_ct_data_nonce"
    # Cutting Plan
    CP_EDIT_PCS    = "cp_edit_pcs"
    CP_EDIT_POS    = "cp_edit_pos"
    CP_EDIT_STYLES = "cp_edit_styles"
    CP_STD_PLANS   = "cp_std_plans"
    # Fabric DB
    FABRIC_DB_DEL_SEL = "fabric_db_del_sel"
    FABRIC_DB_PAGE    = "fabric_db_page"
    # GIII — Excel pipeline
    EXCEL_LOG     = "excel_log"
    EXCEL_RESULTS = "excel_results"
    # GIII — Reports tab
    RPT_ALL_RESULTS    = "rpt_all_results"
    RPT_API_REQS_CACHE = "rpt_api_reqs_cache"
    RPT_BP_BYTES       = "rpt_bp_bytes"
    RPT_CPRS_PREVIEW   = "rpt_cprs_preview"
    RPT_CPRS_TRANSLATE = "rpt_cprs_translate"
    RPT_CPRS_WARNS     = "rpt_cprs_warns"
    RPT_CP_BYTES       = "rpt_cp_bytes"
    RPT_DIM_CODE       = "rpt_dim_code"
    RPT_DIM_ROWS       = "rpt_dim_rows"
    RPT_KL_BYTES       = "rpt_kl_bytes"
    RPT_PCS_BOX        = "rpt_pcs_box"
    RPT_PO_SELECT      = "rpt_po_select"
    RPT_PS_BYTES       = "rpt_ps_bytes"
    # GIII — history
    DEL_POS = "del_pos"
    # GIII — smart upload
    SMART_DETECTIONS = "smart_detections"
    SMART_LOG        = "smart_log"
    SMART_RESULTS    = "smart_results"
    # Production Tracking
    PT_FU_DEL_SEL = "pt_fu_del_sel"
    PT_REMOVE_SEL = "pt_remove_sel"
    PT_TAB_RADIO  = "pt_tab_radio"
    TRACKER_COLS  = "tracker_cols"
    TRK_COLS      = "trk_cols"
    # Sky East
    SE_BP_SEL  = "se_bp_sel"
    SE_GEN_PCS = "se_gen_pcs"
    SE_HIST_PC = "se_hist_pc"
    # Summary
    SUM_GIII_COLS = "sum_giii_cols"
    SUM_SE_COLS   = "sum_se_cols"
    # UPC Check
    UPC_CT_DIR       = "upc_ct_dir"
    UPC_CT_INPUT     = "upc_ct_input"
    UPC_CT_LAST      = "upc_ct_last"
    UPC_LK_HIST      = "upc_lk_hist"
    UPC_LK_INPUT     = "upc_lk_input"
    UPC_LK_LAST      = "upc_lk_last"
    UPC_VF_INPUT     = "upc_vf_input"
    UPC_VF_PO_ACTIVE = "upc_vf_po_active"
    UPC_VF_RESULTS   = "upc_vf_results"


# Allowed values for ``SK.SE_COLOR_SOURCE`` — controls where the buy-plan
# Chinese colour mapping (中文颜色 / 中文颜色代码 / 主标颜色) is loaded from.
COLOR_SOURCE_DB       = "db"        # 🎨 Colors tab — color_translation table
COLOR_SOURCE_PROGRESS = "progress"  # 大货进度表 — HHN Contract No. file
