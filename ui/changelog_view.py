"""Release changelog tab — version history for PO Extractor."""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Changelog data — newest first
# Each entry: {version, date, entries: [{type, text}]}
# Types: feat | fix | perf | refactor | security | docs
# ---------------------------------------------------------------------------
_CHANGELOG: list[dict] = [
    {
        "version": "2.1.2",
        "date": "2026-07-01",
        "entries": [
            {"type": "docs", "text": "Added `docs/HOW_TO_START.md` — a run guide covering how to start the server (foreground / background / fully-detached), the correct Python 3.13 interpreter, health check, how to stop by PID, when a restart is needed after module changes, and troubleshooting for the app not staying up"},
        ],
    },
    {
        "version": "2.1.1",
        "date": "2026-06-19",
        "entries": [
            {"type": "perf", "text": "Sky East Buy Plan: the per-row style normalisation introduced in 2.1.0 is now memoised per distinct style within a sheet — collapsing what was one `_norm_key()` call per data row back down to one call per style (a sheet has at most a base style and its `A` variant)"},
        ],
    },
    {
        "version": "2.1.0",
        "date": "2026-06-19",
        "entries": [
            {"type": "feat", "text": "Sky East Buy Plan: a style ending in **A** (e.g. `DR5302A`) is now placed in the **same sheet** as its base style (`DR5302`) instead of getting its own tab — but only when the base style is also present in the data. Each data row keeps its own style name, so `DR5302` and `DR5302A` stay distinct in column B; the sheet's per-tab total combines both. A standalone `…A` style with no matching base is unaffected. The Buy Plan ↔ 核料 cross-comparison folds the variant onto the base style too, so the Match column stays correct"},
        ],
    },
    {
        "version": "2.0.6",
        "date": "2026-06-18",
        "entries": [
            {"type": "perf", "text": "All 8 main tabs are now wrapped in `st.fragment` — a widget interaction (typing, selecting, clicking) reruns **only its own tab** instead of all 8. Previously `st.tabs` re-executed every tab's data loads and table renders on every interaction anywhere in the app (~8× the necessary work per click)"},
            {"type": "perf", "text": "`BaseSQLiteStore._conn()` now sets `PRAGMA journal_mode=WAL` **once per database per process** instead of on every connection — WAL is a persisted DB property, so re-applying it on each query (≈5× the cost of a bare connect, ~11× per items-table build) was pure overhead"},
            {"type": "refactor", "text": "Dependencies upgraded to latest (Streamlit 1.58.0, pyarrow 24, cryptography 49, and ~24 others); `beautifulsoup4` / `ebcdic` held at the newest versions `extract-msg` (the `.msg` PO parser) supports — environment verified consistent via `pip check`"},
        ],
    },
    {
        "version": "2.0.5",
        "date": "2026-06-17",
        "entries": [
            {"type": "fix", "text": "Sky East processing: `_run_sky_east_processing` now wraps its temp directory in `try/finally` — the temp dir leaked on the early *no contracts parsed* return and on any exception during a run"},
            {"type": "fix", "text": "Sky East **Missing Fields** editor: the Save action now drops the locale-aware Photo column (`_th(\"Photo\")`) rather than the literal `\"Photo\"`, so the image column is correctly removed before saving under the Chinese UI"},
        ],
    },
    {
        "version": "2.0.4",
        "date": "2026-06-17",
        "entries": [
            {"type": "refactor", "text": "Sky East Buy Plan PC No. multiselect simplified to the same single-key pattern used by the Download / Wash Label multiselects — removed the shadow-key + pre-render-snapshot workaround. Structurally eliminates both the deselect-all bug and the stale-delete crash rather than patching them"},
        ],
    },
    {
        "version": "2.0.3",
        "date": "2026-06-17",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: deleting a contract that was selected here no longer crashes the tab — a stale-value guard now cleans the multiselect's widget key before render, matching every other multiselect in the module (`reports_tab` guard fixed to clean the actual widget key, not just the logical mirror)"},
            {"type": "fix", "text": "Sky East Buy Plan: the PC No. selection can now be **fully cleared** — removed a fallback that silently re-added the last deselected PC, which made deselect-all impossible"},
            {"type": "fix", "text": "Buy Plan temp directory is now removed via `try/finally` even if brand registration or image-map building throws mid-generation"},
            {"type": "refactor", "text": "Cross-comparison mismatch count made robust to the emoji label changing in `build_cross_comparison`; removed an unused pandas import; unified download filename thresholds"},
        ],
    },
    {
        "version": "2.0.2",
        "date": "2026-06-17",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: fixed a broken indentation in the **Generate Buy Plan + 核料** handler and a stale `sel` reference — the full buy-plan + 核料 generation block now runs correctly and the output filename uses the effective selection"},
        ],
    },
    {
        "version": "2.0.1",
        "date": "2026-06-17",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: initial fixes for the **Generate Buy Plan + 核料** button staying disabled after uploading 大货进度表 — handling for the multiselect session-state desync that left the selection empty"},
        ],
    },
    {
        "version": "2.0.0",
        "date": "2026-05-26",
        "entries": [
            {"type": "feat", "text": "**Production Stage Tracking** reaches its 2.0 baseline — the new 🏭 Tracking module is now a first-class part of PO Extractor (22 stages across 4 groups, dependency-driven readiness, forward-scheduling planner, and QC inspection tracking)"},
            {"type": "fix", "text": "Tracking: `list_untracked_pos` is now scoped by company (P1) so the Add New picker only offers POs the user is permitted to see"},
            {"type": "fix", "text": "Tracking: inapplicable optional sample stages are excluded from the dashboard Delayed / Blocked metrics (P2) so N/A stages don't inflate at-risk counts"},
        ],
    },
    {
        "version": "1.15.0",
        "date": "2026-05-26",
        "entries": [
            {"type": "feat", "text": "Added the **Production Stage Tracking** module — Stages 0–4: wide-table schema (22 stages, dependency matrix, QC inspections), store layer with `compute_readiness` / `compute_schedule` / `compute_inspection_reminders`, and the 🏭 Tracking tab (Dashboard, Overview, Edit, Add New, Plan)"},
        ],
    },
    {
        "version": "1.14.8",
        "date": "2026-05-25",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan multiselect + multiple bug fixes (merged from the production-delivery-tracking branch)"},
        ],
    },
    {
        "version": "1.14.6",
        "date": "2026-05-25",
        "entries": [
            {"type": "fix", "text": "Sky East → Reports → Download Items: **CSV download crashed** with `NameError: name 'CSV_MIME' is not defined` — `CSV_MIME` was used but never imported from `ui.shared`"},
            {"type": "fix", "text": "Sky East → Reports → Wash Labels: selecting styles in **Style (Fabric Mapping)** mode and then deleting a contract in the History tab wiped all selected styles — the stale-state guard was incorrectly filtering style names against the PC No. set; `se_wl_styles` is now excluded from that guard"},
            {"type": "fix", "text": "Sign-out now resets all generated file bytes (buy plan, 核料 zip, item download, wash label), progress lookup, fabric lookup, and masked zip — previously these persisted across logout, leaking one user's generated data to the next user on the same browser session"},
            {"type": "fix", "text": "Sign-out now clears `_se_bp_prog_fp` (大货进度表 fingerprint key) — previously a second user uploading the same file as the first user would silently skip processing"},
            {"type": "fix", "text": "Session-state defaults in `app.py` now initialize `SE_PROGRESS_LKUP`, `SE_FABRIC_LOOKUP`, `SE_MASKED_ZIP`, and `SE_IMAGES_DIR` — previously missing from the defaults block"},
            {"type": "fix", "text": "Admin → Email: Brevo sender warning now shows a clear message when both Sender and Username are empty (`empty — neither Username nor Sender is set`) instead of rendering an empty backtick pair"},
        ],
    },
    {
        "version": "1.14.5",
        "date": "2026-05-25",
        "entries": [
            {"type": "fix", "text": "Sky East → Reports → Buy Plan: **Generate Buy Plan button now stays enabled** after uploading 大货进度表 — removed the explicit `st.rerun()` after processing the file; the file-upload event already triggers a script rerun, so the extra rerun was causing `se_bp_sel` to remain `[]` when the file was uploaded before PC Nos were selected, keeping the button permanently disabled"},
            {"type": "fix", "text": "Buy Plan: 大货进度表 loaded status message now appears immediately in the same run as the upload (moved caption to read session state after processing rather than before)"},
        ],
    },
    {
        "version": "1.14.4",
        "date": "2026-05-25",
        "entries": [
            {"type": "fix", "text": "Sky East → Reports → Buy Plan: fingerprint guard added to prevent infinite-rerun loop from 大货进度表 file uploader in Streamlit 1.57.0"},
            {"type": "fix", "text": "Sky East → New Contracts → Reference files expander now **defaults to open** — drag-and-drop into file uploaders inside a collapsed expander was unreliable in some browser configurations"},
        ],
    },
    {
        "version": "1.14.3",
        "date": "2026-05-23",
        "entries": [
            {"type": "fix", "text": "Email via Brevo: the SMTP connection was succeeding but emails were **silently dropped** because the From address was the `@smtp-brevo.com` login username rather than a verified sender — Brevo accepts the handshake but never delivers in this case"},
            {"type": "fix", "text": "Admin → Email now shows a clear warning when using Brevo with an unverified sender address, linking to the Brevo senders page to resolve it"},
            {"type": "fix", "text": "Sky East → Reports: email section now shows an inline warning (before the Send button) when the Brevo sender is misconfigured, so the issue is visible without navigating to Admin"},
        ],
    },
    {
        "version": "1.14.2",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Sky East history: **Browse Items** and **Delete Selected** now work reliably — stale session-state values that pointed to deleted PC Nos. were causing a `StreamlitAPIException` on the next render, silently breaking both widgets"},
            {"type": "fix", "text": "`_se_hist_item_browser` strips any pc_nos from `se_hist_pc` session state that are no longer in `pc_options` before the multiselect renders — prevents crash after deletion"},
            {"type": "fix", "text": "`_se_hist_delete_section` clears both `se_del_pcs` and `se_hist_pc` from session state before `st.rerun()` and uses `st.toast` so confirmation persists across the rerun"},
            {"type": "fix", "text": "History section auto-cleans orphaned `pc_no = ''` contracts on every load — these were left by files parsed before the dynamic header fix and appeared as invisible blank options in every multiselect"},
        ],
    },
    {
        "version": "1.14.1",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Sky East parser v1.3: `_find_header_row` now scores every candidate row by counting recognised alias matches — picks the row with the most hits instead of the first row containing any single signal (eliminates false positives when header rows appear late in the sheet)"},
            {"type": "feat", "text": "Header-row signal set is now auto-derived from `_COL_ALIASES` at detection time — adding new aliases to the alias table automatically improves header detection with no separate maintenance"},
            {"type": "feat", "text": "`_map_columns` gains a **Pass 3** partial/substring matcher — if an exact alias fails, any alias ≥ 5 chars that is a substring of the header cell (or vice versa) claims the column; covers near-miss names like 'supplier article number' matching 'article number'"},
            {"type": "feat", "text": "`_COL_ALIASES` substantially expanded: `style_no` (12 variants), `po_number` (13 variants), `color_name` / `color_code` (10+ variants each), `total_qty`, `ex_fty`, `fob_usd`, `article_name`, `fabric_no`, `launch_date` — all with broader synonym coverage"},
            {"type": "feat", "text": "`_HEADER_LABEL_ALIASES` (contract header fields) expanded: `pc_no`, `party_a`, `party_b`, `payment_terms`, `trade_term`, `pc_date` all have more label variants including Chinese, abbreviated, and punctuation-variant forms"},
        ],
    },
    {
        "version": "1.14.0",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Sky East store: `_sizes_to_db_cols()` helper collapses any dynamic size dict (including \"1X\", \"2X\", \"XXXL\", \"SM\", etc.) into the 6 fixed DB columns (xs/s/m/l/xl/xxl) using the `SIZE_TO_DB` mapping from the parser"},
            {"type": "feat", "text": "`_normalize_sizes()` added to store schema — normalises raw parser size keys to the 6 canonical keys before duplicate/change detection, so files with \"1X\"/\"2X\" styles compare correctly against existing DB rows"},
            {"type": "fix", "text": "`_sizes_equal()` updated to normalise both sides before comparison — prevents false \"updated\" records when the same quantities are expressed with different size key names across file versions"},
            {"type": "refactor", "text": "`_insert_item` and `_update_item` now call `_sizes_to_db_cols()` instead of hardcoded `sizes.get(\"XS\", 0)` etc. — any size layout supported without code changes"},
        ],
    },
    {
        "version": "1.13.9",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Sky East parser: contract header reader now scans from the label column rightward instead of assuming the value is always in column E — fixes HHPPC046-style files where the value sits in column D (one column left of the standard layout)"},
            {"type": "fix", "text": "Fallback row positions (pc_no, pc_date, party_b, etc.) now try column D before column E, covering both old and new Sky East file layouts"},
        ],
    },
    {
        "version": "1.13.8",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "GIII Reports → Generate Outputs: added **📋 Create Buy Plan (生产计划单)** button — generates a factory production plan in standard GIII format (one sheet per style, two-row merged header, PO/color rows with size breakdown, Chinese colour lookup, merged cells, footer totals)"},
            {"type": "feat", "text": "New exporter `giii_production_plan.py`: dynamic size columns, standard size ordering, automatic NaN/null handling for fabric/description fields"},
        ],
    },
    {
        "version": "1.13.7",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Completed comprehensive temp-file leak audit — all `mkdtemp()` / `mkstemp()` directories are now cleaned up after every processing run"},
            {"type": "fix", "text": "GIII Smart Upload (`giii_view.py`): detection temp dir now wrapped in try/finally so it is deleted after every page render"},
            {"type": "fix", "text": "GIII Excel pipeline (`excel_extraction.py`): `mask_out_dir`, `tmpdir`, and `out_dir` all cleaned up after run"},
        ],
    },
    {
        "version": "1.13.6",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Sky East processing: `mask_out_dir` and `tmpdir` cleaned up after every order file run"},
            {"type": "fix", "text": "GIII extraction: `tmpdir` and `out_dir` cleaned up in `_run_extraction`, `_run_from_history`, and `_create_buyplan_bytes`"},
            {"type": "fix", "text": "`ProgressLookup` now accepts `data=bytes` — large progress files (144 MB+) are never written to disk, eliminating the primary source of temp-file disk exhaustion"},
        ],
    },
    {
        "version": "1.13.5",
        "date": "2026-05-22",
        "entries": [
            {"type": "perf", "text": "Buy plan generation: `load_workbook()` hoisted outside the 核料 loop — template is parsed once and deep-copied per workbook instead of re-read from disk N times"},
            {"type": "perf", "text": "Image cache: loaded bytes are written back to `st.session_state` so repeated Generate presses re-use in-memory data without disk re-reads"},
            {"type": "perf", "text": "Wash label export: replaced three `iterrows` sweeps with vectorised pandas `drop_duplicates + set_index + to_dict` ops"},
            {"type": "perf", "text": "KL format export: pre-grouped size rows by PO number (O(1) lookup vs O(n) scan per style)"},
            {"type": "perf", "text": "Buy plan font allocation: shared `Font` object cache eliminates per-cell `Font()` construction overhead"},
        ],
    },
    {
        "version": "1.13.4",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: added **Select All** button next to PC No. multiselect so all contracts can be included in one click"},
            {"type": "fix", "text": "Sky East Buy Plan / Download Items / Wash Labels: info message shown when nothing is selected, explaining what to do"},
            {"type": "fix", "text": "Wash Labels: improved guidance message when no fabric mapping is available for style-based generation"},
        ],
    },
    {
        "version": "1.13.3",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Sky East history: Buy Plan buy `out_dir` cleaned up after all file bytes are captured into session state"},
            {"type": "fix",  "text": "Dual-header photo lookup: vectorised style→picture_id dict construction replaces slow `iterrows`"},
        ],
    },
    {
        "version": "1.13.2",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Intermediate release — internal feature work and stability improvements"},
        ],
    },
    {
        "version": "1.9.1",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Added production tracking schema stub for future order-progress integration"},
        ],
    },
    {
        "version": "1.9.0",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "KL format export for Sky East orders"},
            {"type": "feat", "text": "Vendor fax number parsing from order files"},
            {"type": "feat", "text": "Multi-source combined order summary view"},
            {"type": "refactor", "text": "Major UI refactor across Sky East and GIII tabs"},
        ],
    },
    {
        "version": "1.8.5",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Six bugs found in code review — item enrichment, contract save, and display fixes"},
        ],
    },
    {
        "version": "1.8.4",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Progress lookup correctness: legacy column defaults + colour code key normalisation"},
        ],
    },
    {
        "version": "1.8.3",
        "date": "2026-05-08",
        "entries": [
            {"type": "refactor", "text": "Centralised constants + `BuyplanColorLookups` NamedTuple for cleaner lookup passing"},
        ],
    },
    {
        "version": "1.8.2",
        "date": "2026-05-08",
        "entries": [
            {"type": "refactor", "text": "Addressed code review findings across parsers and exporters"},
        ],
    },
    {
        "version": "1.8.1",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "One-time migration sets `default_color_source` to `progress` for existing installs"},
        ],
    },
    {
        "version": "1.8.0",
        "date": "2026-05-08",
        "entries": [
            {"type": "feat", "text": "Progress lookup now uses primary key `PC No · style · color` — more precise contract matching"},
        ],
    },
    {
        "version": "1.7.9",
        "date": "2026-05-08",
        "entries": [
            {"type": "feat", "text": "Color source radio button in Buy Plan section lets users choose between Progress file and Color DB"},
            {"type": "feat", "text": "大货进度表 uploader added directly to Buy Plan section for quick colour lookup"},
        ],
    },
    {
        "version": "1.7.8",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Corrected buy plan left/right page margins to 0.64 cm (0.25 in)"},
        ],
    },
    {
        "version": "1.7.7",
        "date": "2026-05-08",
        "entries": [
            {"type": "feat", "text": "Configurable print margins added to buy plan export"},
            {"type": "feat", "text": "Index 综合key included in fabric description column"},
        ],
    },
    {
        "version": "1.7.6",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Print settings not being applied — fixed by using `pageSetUpPr.fitToPage` flag"},
        ],
    },
    {
        "version": "1.7.5",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Disabled brand-agnostic fallback in colour code lookup to prevent incorrect cross-brand matches"},
        ],
    },
    {
        "version": "1.7.4",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Doubled colour code appearing in BODY COLOR-CN column"},
            {"type": "fix", "text": "Empty 综合key no longer written to fabric index"},
        ],
    },
    {
        "version": "1.7.3",
        "date": "2026-05-08",
        "entries": [
            {"type": "feat", "text": "A4 landscape fit-all-columns print settings applied to all buy plan sheets"},
        ],
    },
    {
        "version": "1.7.2",
        "date": "2026-05-07",
        "entries": [
            {"type": "feat", "text": "Centralised fabric master database — fabric parts stored and queried from a shared DB table across all companies"},
        ],
    },
    {
        "version": "1.7.1",
        "date": "2026-05-07",
        "entries": [
            {"type": "feat", "text": "Admin-configurable default Chinese colour mapping source (Progress file vs Colour DB)"},
        ],
    },
    {
        "version": "1.7.0",
        "date": "2026-05-07",
        "entries": [
            {"type": "feat", "text": "PC No.-keyed colour lookups for precise Sky East colour resolution"},
            {"type": "feat", "text": "Bilingual UI (English / 中文) with language toggle in sidebar"},
            {"type": "feat", "text": "Email delivery — generated buy plan and 核料 files can be sent directly from the app"},
            {"type": "feat", "text": "Combined Chinese colour pipeline: Progress file → Colour DB → buyer PO fallback"},
        ],
    },
    {
        "version": "1.63.4",
        "date": "2026-05-06",
        "entries": [
            {"type": "fix", "text": "COLLATE NOCASE matching in progress-xlsx importer; merges case-duplicate colour rows correctly"},
        ],
    },
    {
        "version": "1.63.3",
        "date": "2026-05-06",
        "entries": [
            {"type": "fix", "text": "Sky East: buyer PO colour_code no longer copied into 中文颜色代码 (separate fields)"},
        ],
    },
    {
        "version": "1.63.2",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "Progress-xlsx importer extended to read `英文颜色` / `中文颜色代码` headers and write back colour codes"},
        ],
    },
    {
        "version": "1.63.1",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "中文颜色 formatted as `#code|name` in HHP buy plan column I for richer colour display"},
        ],
    },
    {
        "version": "1.63.0",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "中文颜色代码 added to colour lookup pipeline and HHP buy plan output"},
        ],
    },
    {
        "version": "1.62.4",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "Added Brevo and Resend email provider presets"},
            {"type": "feat", "text": "SSL port 465 support for SMTP email delivery"},
        ],
    },
    {
        "version": "1.62.2",
        "date": "2026-05-06",
        "entries": [
            {"type": "fix", "text": "Outlook SMTP 535 auth error — added App Password guidance in Admin → Email"},
        ],
    },
    {
        "version": "1.62.1",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "Email provider quick-setup presets (Gmail, Outlook, QQ Mail, etc.) in Admin → Email"},
        ],
    },
    {
        "version": "1.62.0",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "SMTP settings now fully configurable from Admin → Email tab (no config file editing required)"},
        ],
    },
    {
        "version": "1.61.0",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "Email delivery feature — generated buy plan / 核料 files can be emailed to recipients"},
        ],
    },
    {
        "version": "1.60.0",
        "date": "2026-05-05",
        "entries": [
            {"type": "feat", "text": "Initial release of PO Extractor — PDF and Excel purchase order parsing for GIII and Sky East"},
            {"type": "feat", "text": "Buy plan generation, Template_P export, 核料 workbooks"},
            {"type": "feat", "text": "Fabric mapping, colour translation, and wash label generation"},
            {"type": "feat", "text": "Admin panel: users, companies, column mapping, size order, templates"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Type display config
# ---------------------------------------------------------------------------
_TYPE_CONFIG = {
    "feat":     ("🌟", "#0d6efd", "Feature"),
    "fix":      ("🐛", "#dc3545", "Fix"),
    "perf":     ("⚡", "#fd7e14", "Performance"),
    "refactor": ("♻️",  "#6c757d", "Refactor"),
    "security": ("🔒", "#198754", "Security"),
    "docs":     ("📄", "#6610f2", "Docs"),
}


def show_changelog_tab() -> None:
    """Render the Releases / Changelog tab."""
    st.markdown("## 🔖 Release History")
    st.caption("All versions of PO Extractor, newest first.")

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_cols = st.columns(len(_TYPE_CONFIG))
    for col, (ttype, (icon, color, label)) in zip(legend_cols, _TYPE_CONFIG.items()):
        col.markdown(
            f"<span style='color:{color}; font-weight:600'>{icon} {label}</span>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Version cards ─────────────────────────────────────────────────────────
    for entry in _CHANGELOG:
        ver   = entry["version"]
        date  = entry["date"]
        items = entry["entries"]

        # Header row
        st.markdown(
            f"<div style='display:flex; align-items:baseline; gap:0.75rem;'>"
            f"<span style='font-size:1.15rem; font-weight:700;'>v{ver}</span>"
            f"<span style='color:#888; font-size:0.85rem;'>{date}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Change items
        for item in items:
            ttype = item.get("type", "feat")
            icon, color, label = _TYPE_CONFIG.get(ttype, ("•", "#333", ttype))
            st.markdown(
                f"<div style='margin: 0.15rem 0 0.15rem 1rem; font-size:0.92rem;'>"
                f"<span style='color:{color}; font-weight:600; margin-right:0.4rem'>{icon}</span>"
                f"{item['text']}"
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<div style='margin-bottom:0.75rem'></div>", unsafe_allow_html=True)
        st.divider()
