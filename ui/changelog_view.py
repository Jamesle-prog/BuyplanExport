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
        "version": "2.29.0",
        "date": "2026-07-07",
        "entries": [
            {"type": "feat", "text": "**Pipeline convergence phase 2: Sky East contracts now grade their own quality the way GIII POs do.** The parser computes a real confidence score (100 minus 10 per missing contract-header field, replacing the old crude 100-or-50) and a `validation_status` of valid/warning/exception on the same scale as GIII's, so both pipelines' quality grades mean the same thing downstream. The item-level import checks (blank style/color, negative quantities, non-standard HHN, unparseable dates, Config SKU coverage) moved from the upload screen into the backend (`po_extractor/parsers/sky_east_validation.py`) — the UI still shows identical warnings, but the checks are now reusable and testable outside Streamlit"},
        ],
    },
    {
        "version": "2.28.2",
        "date": "2026-07-07",
        "entries": [
            {"type": "refactor", "text": "**Pipeline convergence phase 1: Sky East now goes through the same front door as GIII.** The universal file detector recognizes Sky East purchase contracts by content (same keyword signature the parser locks onto), a canonical `parse_sky_east_order()` lives in the parsers facade alongside `parse_pdf()` (the Sky East upload flow now calls it instead of importing parser internals), and the superseded hardcoded-layout Sky East parser is no longer exported. Sky East is also registered as an Excel format on its company entry, so format→company resolution works for it like it does for the PDF formats"},
        ],
    },
    {
        "version": "2.28.1",
        "date": "2026-07-07",
        "entries": [
            {"type": "fix", "text": "**All Orders: GIII's Contract No. now comes from the HHN 大货进度表 progress records** instead of just mirroring the PO number. Matched by the progress sheet's PO# column first (normalized, so casing/whitespace differences don't matter), falling back to a style match when PO# is blank — and left empty when the progress data has no row for the order, rather than showing a misleading value. Upload the 大货进度表 per company via the HHN Contract Progress tab to populate it"},
        ],
    },
    {
        "version": "2.28.0",
        "date": "2026-07-07",
        "entries": [
            {"type": "feat", "text": "**Summary → new 🧾 All Orders sub-tab: every client's orders in one combined table with standardized columns.** GIII POs and Sky East contract items previously lived in separate lists with different headers; they now map into one standard column set (Company, PO Number, Contract No., Style, Color, Brand/Customer, Factory, COO, Order Date, Ex-Fty Date, Units, Unit Price, Total Cost, Season, Source) with client filter, PO/contract/style/color search, a column picker, and a single-sheet Excel download. Fields one client can't provide stay blank rather than shifting the header, so the layout is identical no matter which clients contribute rows. Company-permission gating matches the rest of the Summary tab"},
            {"type": "refactor", "text": "The standard column mapping lives in a new backend module (`po_extractor/ui_helpers/combined_summary.py`) with adapters per pipeline, so future views and exporters can reuse the same standardized shape instead of hand-mapping each client's schema — first step of the GIII/Sky East structural-convergence plan's shared read-side model"},
        ],
    },
    {
        "version": "2.27.8",
        "date": "2026-07-06",
        "entries": [
            {"type": "fix", "text": "**Update.bat would have overwritten user-customized settings with factory defaults.** The updater's protect-list only covered databases and account/license files — but companies, size order, output schema, custom fibers, and the buy-plan template workbooks are all edited at runtime through the app's admin screens AND ship in the pack, so an update would have silently reset them. The `data\\` directories and `auth\\companies.json` are now excluded from the copy wholesale, so a future runtime-editable file can't reintroduce the bug by being forgotten. Verified with an adversarial test where the pack deliberately carried factory versions of every such file"},
            {"type": "fix", "text": "**Update/Uninstall couldn't tell the app was running.** Their check matched the process command line, but `Start_PO_Extractor.bat` launches Python via a relative path, so the command line never contains the install folder — the scripts always said \"Not running\" and Uninstall could then die mid-removal on the locked `.venv\\python.exe`. Detection now matches the process's executable path, which is always absolute"},
            {"type": "fix", "text": "Install/Update now verify each native step actually succeeded (venv creation, pip install, license registration) instead of printing \"complete!\" even after e.g. a network failure — PowerShell's error handling doesn't cover native commands' exit codes"},
            {"type": "security", "text": "Uninstall's full-wipe (`DELETE`) path now also removes `auth\\smtp_settings.json` (which can hold an SMTP password), `auth\\companies.json`, and `po_extractor\\data\\custom_fibers.json` — a \"remove everything\" run no longer leaves a credential file behind"},
            {"type": "fix", "text": "Install's Python detection no longer trips over the `*` default-interpreter marker in `py -0p` output when 3.13 is the system default (the captured path started with `*` and failed validation, falling back to guessed install locations)"},
        ],
    },
    {
        "version": "2.27.7",
        "date": "2026-07-06",
        "entries": [
            {"type": "feat", "text": "**Added an updater to the install pack** (`Update.bat` / `Update.ps1`). Run it from a newly-extracted pack folder, point it at an existing install, and it copies in the new app code and refreshes dependencies — `data\\`, `auth\\users.json`, `auth\\license.key`, `auth\\smtp_settings.json`, and `.venv\\` are explicitly excluded from the copy and never touched, even if a future pack happened to contain files by those names. Verified with a smoke test where the source pack deliberately included conflicting files under those exact names, to confirm the exclusion is defensive rather than incidental"},
        ],
    },
    {
        "version": "2.27.6",
        "date": "2026-07-06",
        "entries": [
            {"type": "fix", "text": "**Resetting an existing user's password via `setup_users.py` silently demoted admins back to a regular user.** `create_user()` always wrote whatever `role` it was given, defaulting to `user` — unlike `companies`/`modules`/`email`, it never fell back to the account's existing role when the caller didn't specify one. Since `setup_users.py` never passed a role except for the very first bootstrap account, re-running it against an existing admin (e.g. to change their password) quietly took away their admin access with no warning. `create_user()` now preserves the existing role when none is given, same as its other fields; explicitly passing a role (the admin User Management screen, and the first-run bootstrap) still overrides it as before"},
        ],
    },
    {
        "version": "2.27.5",
        "date": "2026-07-06",
        "entries": [
            {"type": "security", "text": "**This machine's `auth/license.key` had been committed to git** — `.gitignore` excluded `auth/license_key.txt`, but the file the app actually writes is `auth/license.key`, so the typo never matched and every clone/archive carried this dev machine's hardware-fingerprint key. Fixed the filename in `.gitignore` and untracked the file (kept on disk locally — the running app is unaffected). Not a live exposure risk in practice since `Install.ps1`/`docs/DEPLOYMENT.md` both regenerate a fresh key unconditionally on setup, but it had no business being in git history going forward"},
        ],
    },
    {
        "version": "2.27.4",
        "date": "2026-07-06",
        "entries": [
            {"type": "feat", "text": "**Added an uninstaller to the install pack** (`Uninstall.bat` / `Uninstall.ps1`). Always removes the Python environment (`.venv`) and this computer's license, since both rebuild automatically on the next install. Your PO history, fabric database, and login accounts are kept by default — typing `DELETE` at the prompt is required to also erase those. Deleting the install folder itself and uninstalling Python 3.13 are left as manual steps, since the script can't safely remove files it's running from and Python may be shared with other software on the machine"},
            {"type": "chore", "text": "The install pack's helper scripts (`Install.ps1`, `Install.bat`, `Start_PO_Extractor.bat`, the new uninstaller, `INSTALL_README.md`) are now tracked under `installer/` in this repo instead of only existing in an ad-hoc build folder, so rebuilding the distributable pack no longer depends on that folder still being around"},
        ],
    },
    {
        "version": "2.27.3",
        "date": "2026-07-06",
        "entries": [
            {"type": "fix", "text": "**`setup_users.py` had no way to create the first admin account.** It always created accounts as role `user` (the default on `create_user()`), so a brand-new install — including from the installer pack — had no login that could reach the User Management screen without hand-editing `auth/users.json`. On a fresh install (no accounts yet), the very first account created is now automatically made admin; every account after that still defaults to a regular user as before"},
        ],
    },
    {
        "version": "2.27.2",
        "date": "2026-07-04",
        "entries": [
            {"type": "docs", "text": "**Sky East User Guide: added a \"Buy Plan Only Accounts\" section** (all three versions — bilingual, English, Chinese) covering the restricted role's actual screen: one \"Sky East\" tab, only New Contracts + 📦 Generate / Export sub-tabs, and Generate / Export going straight to Buy Plan + 核料 with no mode picker. A callout near the top now points readers to the right section for their account type"},
            {"type": "fix", "text": "**Sky East User Guide's own Step 4 was out of date** — it claimed the New Contracts \"Process\" button generates the Buy Plan/核料 workbooks directly. That moved to a separate 📦 Generate / Export sub-tab a few releases ago; the button is now named **Process Sky East Files** and only saves the contract. Corrected the button name and the description in all three guide versions and pointed readers to Generate / Export for the actual output step"},
        ],
    },
    {
        "version": "2.27.1",
        "date": "2026-07-04",
        "entries": [
            {"type": "docs", "text": "Added `docs/DEPLOYMENT.md` — a runbook for installing the app as a persistent Windows Service (NSSM: auto-start on boot, auto-restart on crash, rotated logs) instead of running it manually in a terminal. Covers getting the code onto a server, the Python/venv setup, first-run licensing and user setup, the firewall rule, a post-deploy verification checklist, and the update/rollback procedure"},
        ],
    },
    {
        "version": "2.27.0",
        "date": "2026-07-04",
        "entries": [
            {"type": "feat", "text": "**Tracking → Add New can now track Sky East orders, not just GIII.** The untracked-PO picker only ever queried the GIII pipeline's tables, so a Sky East order could never be offered no matter which company you had access to. It now also pulls from Sky East's item table, and a new **Client** filter appears whenever more than one client has untracked orders, so a mixed list doesn't get unwieldy"},
            {"type": "fix", "text": "The 🏭 Tracking sub-tab labels (Dashboard/Overview/Edit Record/Add New/Plan) didn't translate under the Chinese UI — they're rendered via a radio's `format_func`, which the i18n coverage audit couldn't see since the string isn't a literal argument to `t()`. Added their translations explicitly"},
        ],
    },
    {
        "version": "2.26.5",
        "date": "2026-07-03",
        "entries": [
            {"type": "feat", "text": "**Every menu, tab, and admin screen now has full Chinese coverage.** Reference Data, GIII, Sky East, Summary, Tracking, Colors, Fabric DB, and every Admin sub-tab (Users, Companies, Templates, Pipeline Layouts, Size Order, Email, Translations, Settings) — plus the top navigation bar, sidebar, and login form — are wrapped for translation; **793 new Chinese translations** were added so switching to 中文 (🌐) actually shows Chinese everywhere instead of leaving most of the app in English. File names stay English as before"},
            {"type": "fix", "text": "**Tracking → Add New crashed with `UnboundLocalError: cannot access local variable 't'`.** A `for t in targets:` loop inside `_render_add_tab` shadowed the module's `t()` translator for the whole function — Python treats a name assigned anywhere in a function as local throughout, so the `t(\"Overall Notes\")` call earlier in the same function broke every time the tab was opened. Renamed the loop variable and swept the entire codebase for the same hazard (none remain)"},
        ],
    },
    {
        "version": "2.26.4",
        "date": "2026-07-03",
        "entries": [
            {"type": "refactor", "text": "**Chinese-UI coverage sweep.** Tab-bar menus and section headers across the GIII, Sky East, Order Summary, GIII Generate/Export, and admin Translations views are now t()-wrapped, so their tab labels, subheaders, captions, buttons, and status messages translate under the Chinese UI. Radio/selectbox option values compared or stored in code stay English; only their labels are wrapped"},
        ],
    },
    {
        "version": "2.26.3",
        "date": "2026-07-03",
        "entries": [
            {"type": "fix", "text": "**Parser accuracy batch.** Whole-number discounts are no longer 10× smaller (\"1.5%\" became \"0.1.5%\"); multi-word countries/ports survive (\"Sri Lanka\", \"Ho Chi Minh\" were truncated to their first word); 13-digit EAN barcodes and quantities with thousands separators no longer silently drop their size rows; the AI (DeepSeek) parser asks for and stores the real per-row colour instead of filling every row with the division code; the EAN lookup warns loudly when it falls back to fixed column positions"},
            {"type": "fix", "text": "**Price masking is trustworthy again.** Masked `.xlsm` files keep their macros (previously re-packaged as plain xlsx under the .xlsm name — Excel refused to open them), legacy `.xls` fails with a clear message instead of vanishing, and every masking failure now shows in the processing log / on screen instead of a console print nobody sees — a file can no longer silently go missing from the masked zip"},
            {"type": "fix", "text": "**Colors tab: deleting the right rows, keeping manual shades.** The 🗑 delete checkbox now pairs each row with its database id (removing a row inline used to shift every row down and delete the wrong record), and re-importing a 大货进度表 no longer blanks a manually set light/dark shade the keyword classifier can't derive"},
            {"type": "fix", "text": "**Extraction tabs can't serve stale results.** All four fax/portal sections (MSG · KL · TK EU · InforNexus) now tie their results to the uploaded file set — swapping files without re-extracting drops the old table and its download instead of silently offering the previous batch. FOB values that aren't clean numbers degrade gracefully in the summary sheets instead of crashing the export, and non-price FOBs no longer display as \"$NOT CONFIRMED\"/\"$?\""},
            {"type": "fix", "text": "Concurrent-use hardening: simultaneous saves of the same PO serialize (no more lost archive rows / duplicate history), first-run schema migrations tolerate two sessions racing (`duplicate column` crash), buy-plan sheets whose styles collide at 31 chars no longer swap photos, cross-check totals find the Total header on any row (configurable templates read 0 before), production-plan styles containing `/` export instead of crashing, and blank-colour size rows are counted instead of dropped"},
            {"type": "security", "text": "The admin Email panel no longer round-trips the stored SMTP password into the browser on every render (leave blank to keep it), sign-in timing no longer reveals whether a username exists, and the sole remaining admin can no longer demote themselves into a lockout"},
            {"type": "perf", "text": "The styled PO-Tracker workbook is cached instead of being rebuilt on every filter click (Summary tab and GIII Generate/Export)"},
            {"type": "refactor", "text": "**Convention sweep:** GIII extraction sections + Tracking/Summary views now use SK session-key constants (state resets properly on sign-out), user-facing text is t()/_th()-wrapped for the Chinese UI, and every DB-driven multiselect uses the seed-once + stale-value-guard idiom (`guard_multiselect_state` in ui/shared.py) instead of the banned key=+default= pattern"},
        ],
    },
    {
        "version": "2.26.2",
        "date": "2026-07-03",
        "entries": [
            {"type": "fix", "text": "**Fabric DB auto-migration actually runs now.** A fresh deployment silently got an *empty* fabric master (blank 综合key/composition in every buy plan): the store's own schema migrations stamped the same `user_version` values the factory used as its \"legacy copy done\" marker, so the copy from `po_history.db` was unreachable. The marker now uses a dedicated bit; locked by a new regression test"},
            {"type": "fix", "text": "**Photo injection can no longer delete a finished buy plan.** When no sheet matched the photo map (e.g. every photo style contained `&` — sheet titles were compared XML-escaped), the injector removed the export before discovering there was nothing to move. Titles are now unescaped and the workbook is only replaced when the patched copy exists"},
            {"type": "fix", "text": "**核料 colour column no longer misdetected.** An always-true guard (string-vs-int comparison) overrode a correctly detected 颜色/Color header with the leftmost other column whenever the size-header row contained any extra label (e.g. 合计)"},
            {"type": "fix", "text": "**Sky East contracts missing an optional header row (e.g. Trade Term) no longer fail entirely** with a cryptic `'trade_term'` error — absent fields default to blank and the file's items import normally (parse confidence drops as before)"},
            {"type": "fix", "text": "**Sky East style photos are read from the actual contract sheet.** Image positions were always taken from sheet 1 even when the contract was found on a later sheet, attaching wrong or missing photos"},
            {"type": "fix", "text": "**KL/MSG extraction: HTS codes with repeated digits are no longer corrupted** (6110.20.2079 became 610.20.2079). De-doubling is now applied only when the match is genuinely fax-doubled (doubled dots)"},
        ],
    },
    {
        "version": "2.26.1",
        "date": "2026-07-03",
        "entries": [
            {"type": "security", "text": "**A non-admin with no assigned companies now sees nothing instead of everything.** The Summary tab, GIII PO History, GIII Generate/Export, and the GIII exception badge passed an empty company list through to an *unfiltered* query (the stores treat an empty list as \"no filter\"), so a freshly created user saw every company's POs including unit/extended costs. All four now show the same \"No companies assigned\" notice the Tracking tab already used"},
            {"type": "security", "text": "**Failed sign-ins are now rate-limited.** 5 wrong passwords for a username lock it out for 60 s with exponential backoff (cap 15 min), plus a global brake against username spraying — previously unlimited guesses were possible against the network-reachable login"},
            {"type": "fix", "text": "**Tracking → Edit Record: Delete no longer throws a StreamlitAPIException.** Confirm Delete assigned to the record selectbox's own session key after the widget was rendered (forbidden by Streamlit) — the record *was* deleted, but the error screen replaced the success message. The selection now reconciles automatically and a proper \"Record deleted.\" confirmation shows after the rerun"},
        ],
    },
    {
        "version": "2.26.0",
        "date": "2026-07-03",
        "entries": [
            {"type": "feat", "text": "**Tracking: lab-dip gates for bulk purchasing.** Trim Layout must now be confirmed before Trim Purchase, and Fabric Color (LD) before Fabric Purchase — both gates are ON by default (new *and* existing records) and editable per record in the dependency matrix. Trim Purchase and Fabric Purchase show a readiness badge in the Edit form (✅ Ready / ⏳ Waiting on …), and Group A stages are re-ordered so each confirmation stage sits directly above the purchase it gates"},
            {"type": "perf", "text": "**Faster tab renders on SQLite-heavy screens.** `PRAGMA journal_mode=WAL` (a persisted DB property) now runs once per database file per process instead of on every connection (≈5× a bare connect); the Production Tracking store's schema check is likewise memoized per process, and the store instance is cached via `functools.cache` in `ui/stores.py` — reads still open fresh connections, so data freshness is unchanged"},
            {"type": "refactor", "text": "The AS400 fax-copy parser helpers (`_undouble`, size-code regexes, line-item patterns) previously copy-pasted in the MSG, KL, and TK EU extractors now live once in `ui/giii/_shared.py`; header-field parsing runs each `grep` once instead of twice per field"},
            {"type": "fix", "text": "**MSG extraction: FOB price is now read only from the FOB line** — previously the first doubled `$$` amount anywhere in the PO could be picked up (e.g. an MSRP), and the UNCONFIRMED check now takes priority. InforNexus PO-number fallback no longer uses a redundant `O` in its letter-to-zero substitution"},
            {"type": "security", "text": "`auth/users.json` and `data/fabric_master.db` are no longer tracked by git (local files kept; both added to `.gitignore` along with the fabric DB's WAL/journal side-files and `data/extracted_images/`)"},
        ],
    },
    {
        "version": "2.25.0",
        "date": "2026-07-03",
        "entries": [
            {"type": "feat", "text": "**Per-user tab restrictions.** Admin → Users now has an **Allowed tabs** picker (leave empty = all tabs, same convention as Allowed companies). A new **\"Sky East — Buy Plan only\"** option narrows a user's entire app down to Upload + Generate/Export, pinned to Buy Plan + 核料 mode — Contract History, Missing Fields, Item Data, Wash Labels, and every other top-level tab (GIII, Fabric DB, Reference Data, Colors, Summary, Tracking) stay hidden for that user"},
        ],
    },
    {
        "version": "2.24.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Memory management** to keep RAM and disk bounded (`ui/memory.py`). Automatic: the persistent `extracted_images` folder is pruned to a file-count + total-size cap (oldest first) after each processing run, and the in-memory style-photo cache is trimmed to a cap after processing / buy-plan generation (safe — misses reload from disk). Manual: a new sidebar **🧹 Memory (~N MB)** control shows the approximate size of held blobs (cached downloads + photo cache) and a **Free memory now** button that drops them and clears the AI colour caches without signing out"},
        ],
    },
    {
        "version": "2.23.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Style photos now survive restarts.** Images extracted from Sky East source spreadsheets are saved to a persistent `data/extracted_images` folder (as well as your configured image folder), and the buy-plan generator falls back to it when a photo isn't in the primary folder. Previously extracted images lived only in memory + the configured folder, so a server restart (or a changed/emptied folder) left the buy plan with no pictures until you re-processed"},
            {"type": "feat", "text": "**The buy plan now warns exactly which styles have no photo** — e.g. \"🖼 3 style(s) have no photo in the buy plan: DR5124, DR4578, …\" — instead of silently shipping an image-less workbook, with a hint to re-run Process or drop a `<style>_front.png` into the image folder"},
        ],
    },
    {
        "version": "2.22.2",
        "date": "2026-07-02",
        "entries": [
            {"type": "fix", "text": "**The colour-resolution issues log no longer shows the same miss over and over.** The log is append-only (a fresh row per generation run), so re-running the buy plan stacked identical rows — e.g. DR5124 \"(dark blue)\"→Navy appeared once per run. The table now shows one row per distinct miss (same PC · contract · style · PO · colour · source), keeping the most recent timestamp; the \"N unresolved colour(s)\" counts reflect the de-duplicated total. The underlying log stays a full audit trail, and 🗑️ Clear still wipes it"},
        ],
    },
    {
        "version": "2.22.1",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Tracking → Edit Record is no longer a ~40-row wall.** Stage groups A (Pre-Production), C (Production), and D (Post-Production) are now collapsible panels whose labels carry a live done-count (e.g. \"🧵 Group A — Pre-Production · 5/8 ✅\"); fully-completed groups collapse automatically so the form stays focused on stages that still need work (values in collapsed groups are still saved). Group B keeps its heading (it hosts the Optional Samples panel, which can't nest) but shows the same done-count. A one-line legend above the groups explains what A/B/C/D mean"},
        ],
    },
    {
        "version": "2.22.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Sky East Generate / Export is now one flat screen.** The three sub-tabs (Buy Plan + 核料 · Item Data · Wash Labels) are replaced by a single \"What do you want to generate?\" selector, and ONE shared PC-No. selector serves every output type — switching between buy plan, item downloads, and wash labels no longer loses your PC selection or requires re-picking it three times. Wash Labels keeps its own \"Select by\" modes (PC No. / Style / Upload); when a non-PC mode is chosen a caption clarifies the shared PC selection isn't used. A selection made under the old sub-tabs is migrated automatically"},
        ],
    },
    {
        "version": "2.21.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Processing logs can no longer hide failures.** The GIII and Sky East \"Processing log\" expanders now auto-open with an issue count in the label (e.g. \"Processing log (2 ⚠️)\") whenever any log line carries an error/warning marker — a run with problems no longer looks identical to a clean one. Shared helper `show_processing_log()` in `ui/shared.py`"},
            {"type": "feat", "text": "**GIII's \"📊 Reports\" sub-tab is renamed \"📦 Generate / Export\"** to match Sky East (both regenerate downloadable files from stored data), and the 📦 emoji now consistently means output while 📤 stays reserved for uploads. GIII/Sky East sub-tab labels are wrapped in `t()` so the 🌐 Chinese toggle can translate the navigation"},
            {"type": "fix", "text": "**Chinese-mode i18n gaps closed** in the Sky East results screen (Processing Results, New/Amended item headings, style-photo captions), the buy-plan panel's newer strings (hand-off, pre-flight fabric-code note, colour source/recognition mode line, cross-comparison hints, 大货进度表 status), and the Tracking QC labels — all now wrapped in `t()` with English fallback"},
            {"type": "fix", "text": "**Consistent thousands separators** on Tracking dashboard and Colors tab metrics; Tracking's Edit Record selector now shows how many records it holds"},
            {"type": "fix", "text": "**Large import changesets are no longer invisible**: the Reference Data diff panels keep auto-collapsing above 30 changes, but the label now carries the full field-change count plus a visible \"open to review all N changes\" caption. The Colors audit-log clear now uses a persistent two-step confirm — the button changes to \"Confirm clear (N entries)\" with a Cancel option, instead of a transient warning that silently stayed armed"},
            {"type": "feat", "text": "**\"What lives where\" captions** on the three reference-data tabs (🧵 Fabric DB · 📐 Reference Data · 🎨 Colors) so it's clear which tab holds fabric properties vs style→fabric assignments vs colour translations"},
        ],
    },
    {
        "version": "2.20.1",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**The \"Generating…\" box now states which colour source and recognition mode the run is using** — e.g. \"🎨 Colour source: **大货进度表** · Recognition: **Local + AI Enhance**\" (or \"Local only\", or a warning if AI Enhance is on but no API key is configured) — so it's clear at a glance whether the AI fallback is active"},
            {"type": "feat", "text": "**Renamed the Sky East \"📊 Reports\" tab to \"📤 Generate / Export\" and moved it to second position** (right after New Contracts), so the primary output step reads as an action and follows the natural Upload → Generate flow instead of being buried after Contract History"},
        ],
    },
    {
        "version": "2.20.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Sky East ease-of-use pass.** After processing new contracts, a clear \"✅ Saved N PC No.(s) — next step: 📊 Reports → Buy Plan + 核料\" hand-off now points users to the generation step (previously it wasn't obvious that generation lived in a different tab)"},
            {"type": "feat", "text": "**Exporter diagnostics now surface in the UI, not just the server log.** Missing fabric-master HHN codes and the 主标颜色 mismatch/missing warnings are captured during generation and shown as ⚠️ warnings under the buy plan. The buy-plan download caption now reads \"⚠️ N unresolved colour(s)\" when colours failed to resolve, so a green download button can't hide misses"},
            {"type": "feat", "text": "**Pre-flight fabric-code check.** Before you generate, the Buy Plan panel now flags styles with no fabric code (accounting for saved fabric mappings) — \"N style(s) have no fabric code — 核料 will skip them\" — so 核料 gaps are caught up-front instead of being discovered as a silent omission"},
            {"type": "feat", "text": "**Cross-comparison mismatches are now actionable** — when buy-plan and 核料 totals disagree, the UI names the styles that produced no 核料 output (the usual \"no fabric code\" cause) and points at where to fix them"},
            {"type": "fix", "text": "**Clarified the misleading \"Total Styles\" metric.** It counted style·colour combinations, not distinct styles. The Buy Plan panel now shows both **Styles** (distinct style numbers) and **Style·Colours** (combos) with tooltips, and the Contract History summary column is renamed to **Style·Colours**"},
            {"type": "fix", "text": "**Buy-plan / 核料 filenames now carry a date-time stamp** (e.g. `SkyEast_..._BuyPlan_20260702-1530.xlsx`) so regenerating doesn't silently overwrite the previous download. Also clarified that the New Contracts colour-source radio only sets the Buy Plan default, and that the 大货进度表 uploaded there is one-off (save it in 📐 Reference Data to reuse)"},
        ],
    },
    {
        "version": "2.19.2",
        "date": "2026-07-02",
        "entries": [
            {"type": "refactor", "text": "Removed the redundant 大货进度表 file-uploader from the Sky East Buy Plan panel. The 大货进度表 is managed centrally in **📐 Reference Data → HHN Contract Progress**, so the buy-plan panel now only reports which saved data the run will use (colour resolution already fell back to the saved data automatically — this just removes a duplicate, confusing second upload point)"},
        ],
    },
    {
        "version": "2.19.1",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**主标颜色 is now left genuinely blank when no label colour is on file, instead of being auto-derived.** Following on from the cross-check in v2.19.0: the light/dark heuristic is no longer used to *fill* the value at all — only to cross-check an on-file value. When neither 大货进度表 nor the internal DB has a 主标颜色 for an item, the cell stays empty (not a guessed 白色/黑色), gets a \"missing — enter manually\" comment, and the export raises an end-of-run warning listing the affected items. A guessed label can no longer be mistaken for a confirmed one"},
        ],
    },
    {
        "version": "2.19.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**主标颜色 (main label colour) is now cross-checked against the light/dark heuristic and flags disagreements.** 大货进度表's 主标颜色 is used verbatim (it was already authoritative), but the derived light/dark value is no longer just a silent fallback — it now cross-checks 大货进度表's value. When they disagree (e.g. 大货进度表 records 白色 for a \"Navy\" body colour, which the heuristic reads as 黑色), 大货进度表's value is kept but the cell gets a diagnostic comment and the export raises an end-of-run warning listing every mismatch, so a data-entry slip in 大货进度表 surfaces for review instead of shipping unnoticed. The heuristic is still used only as a last-resort fill when neither 大货进度表 nor the internal DB has a label colour"},
        ],
    },
    {
        "version": "2.18.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**核料 (Template_P) size columns now follow the order's actual size range instead of the template's fixed header.** The shipped Template_P header only defines S/M/L/XL, so any XS or XXL/2XL quantities were silently dropped from the 核料 workbooks. The size columns are now laid out from the sizes that actually appear in the order (canonical XS→XXL order, anchored at the template's first size column): a size the order uses always gets a column, and a size it never uses isn't shown as an empty column (and leaves no orphaned L/XL header). An explicit `size_column_map` in `Sky_East_P_config.json` still wins for admins who pin columns"},
        ],
    },
    {
        "version": "2.17.1",
        "date": "2026-07-02",
        "entries": [
            {"type": "refactor", "text": "Decomposed the 631-line `export_sky_east_buyplan` (down to 365 lines) into focused, unit-testable module-level helpers: `_prefetch_boat_sample_cache`, `_prefetch_fabric_master_cache` + a `_FabricMasterCache` class (the old nested `_display_key_for` closure is now a method), `_fill_fabric_header`, and `_fill_one_style_row` (the per-row writer, threaded via a `_RowContext`). Behaviour is unchanged — the produced workbooks are identical. Replaced the `from _sky_east_helpers import *` wildcard (a documented `NameError` footgun) with an explicit 23-name import. 13 new fast unit tests exercise the extracted helpers directly, without generating a whole workbook"},
        ],
    },
    {
        "version": "2.17.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "fix", "text": "**核料 (Template_P) workbooks now flag unresolved colours the same way the buy plan does.** Previously a colour that failed to resolve was written into the 核料 label as e.g. `Black(未找到)`, with no entry in the colour-resolution log — so a mismatch that was loud in the buy plan was silent (and messy) in 核料. Now the cell shows the English colour alone, carries a diagnostic comment (client's PO colour + 大货进度表's own colour on file), and is recorded in the colour-miss log, mirroring the main buy plan"},
            {"type": "fix", "text": "**核料 workbooks are no longer produced with a malformed stylesheet.** The per-fabric copy used `copy.deepcopy()`, which yielded a workbook whose saved stylesheet referenced a non-existent font — openpyxl (and Excel's repair check) rejected it on reload. It now re-opens the template from an in-memory buffer instead: clean, reloadable output, still no disk re-read, ~1 ms/fabric slower"},
            {"type": "refactor", "text": "De-duplicated the ~19-line \"Local + AI Enhance\" settings auto-fetch that was copy-pasted across both Sky East exporters into one `_resolve_ai_enhance_settings()` helper; de-magic'd the hardcoded 船样要求 column (now resolved from the detected template layout, falling back to column P). Fixed the `export_sky_east_buyplan` docstring, which claimed it returns a path when it returns a `(path, style_totals)` tuple"},
        ],
    },
    {
        "version": "2.16.5",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**Local + AI Enhance colour matching returned no match for genuinely correctable cases (e.g. \"dark brown\" vs 大货进度表's \"Dk Brown\") when the `deepseek-reasoner` model was selected.** `deepseek-reasoner` spends part of its `max_tokens` budget on a hidden reasoning trace before writing the visible answer — the 64/128-token budget sized for a short chat-model answer was being fully consumed by reasoning, truncating the response (`finish_reason: \"length\"`, empty content) before any JSON answer was written. Confirmed live: a 64-token budget produced empty content with all 64 tokens spent on reasoning, while 1024 completed normally with the correct answer. New `max_tokens_for()` in `po_extractor/utils/deepseek_client.py` raises the floor to 1024 for reasoning models at both `color_ai_enhance.py` call sites"},
        ],
    },
    {
        "version": "2.16.4",
        "date": "2026-07-01",
        "entries": [
            {"type": "security", "text": "**Local + AI Enhance was silently matching genuinely different colours as if they were the same** — the AI prompt explicitly told the model to \"treat synonyms as the same (e.g. 'Navy' = 'Dark Blue')\", so a client's \"Dark Blue\" order line got assigned 大货进度表's \"Navy\" colour code, a wrong result presented as a confident match. Rewrote the prompt to allow ONLY spelling/formatting variants of the identical name — typos (\"Daek Blue\" → \"Dark Blue\"), abbreviations of the same name (\"DK Brown\" → \"Dark Brown\"), and formatting differences (case, spacing, a numeric code prefix) — while explicitly forbidding matches across different colour names (Navy/Dark Blue, Cream/White, etc.) even when related or visually similar. An honest 未找到 is safer than a wrong colour code silently assigned to an order"},
            {"type": "docs", "text": "Renamed/reworked the misleading `test_match_color_to_candidates_picks_synonym` test to test the actually-intended typo-correction case, and added a regression guard directly on the prompt text so the old \"treat synonyms as the same\" instruction can't silently come back"},
        ],
    },
    {
        "version": "2.16.3",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**AI Extraction / Local + AI Enhance failed silently whenever the DeepSeek `deepseek-reasoner` model was selected.** Every DeepSeek call (PO PDF extraction, the admin \"Test API key\" button, and colour recognition/matching) unconditionally sent `temperature=0`, but `deepseek-reasoner` rejects that parameter — the call errors out, and the error was swallowed and treated as a plain \"no result\". New shared `po_extractor/utils/deepseek_client.py` (`chat_kwargs()`) omits `temperature` for reasoning models across all three call sites"},
            {"type": "fix", "text": "**A failed AI-enhance colour lookup was being cached forever.** `recognize_colors()`/`match_color_to_candidates()` cached *every* outcome, including API errors and \"no match\" answers — so a colour that failed once (e.g. due to the reasoner-model bug above, or a missing key at the time) stayed stuck at 未找到 for the rest of the server's uptime even after the underlying problem was fixed, since it was never retried. Only genuine successes are cached now; a failure is retried on the next generation"},
            {"type": "docs", "text": "8 new tests: the shared `chat_kwargs()`/`is_reasoning_model()` helpers, that `recognize_colors()`/`match_color_to_candidates()`/`_call_deepseek()` all omit `temperature` for `deepseek-reasoner`, and that a transient failure in either colour-AI function doesn't block a subsequent retry"},
        ],
    },
    {
        "version": "2.16.2",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**DeepSeek AI Extraction / Local + AI Enhance were both broken** — the `openai` package (the OpenAI-compatible client both features use to call DeepSeek) was never added to `requirements.txt`/`requirements.lock` and wasn't installed, so \"Test API key\" failed with `No module named 'openai'` regardless of a valid key. Installed the package and pinned it (and its transitive dependencies: httpx, pydantic, distro, jiter, etc.) in both requirement files so a fresh environment install includes it"},
        ],
    },
    {
        "version": "2.16.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**Colour resolution issues log now also shows 大货进度表's own colour(s)**, alongside the client's PO colour — the same comparison already shown in the Excel cell comment, now visible in the reviewable table too without opening the buy plan"},
            {"type": "docs", "text": "New `progress_colors` column on `sky_east_color_misses`, with an ALTER TABLE migration for existing databases (older rows show blank, never crash or drop data). 6 new tests: storing/joining/blanking progress_colors, the migration path against a pre-existing DB, and an end-to-end naming-mismatch check"},
        ],
    },
    {
        "version": "2.16.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**\"Local + AI Enhance\" now bridges colour-name mismatches between the order file and 大货进度表.** When an exact (客人PC NO · 款式 · 英文颜色) match misses but that PC No. + style *does* have colour(s) on file, the API is asked to pick which of those **actual recorded colours** the client's colour refers to — resolving the common cases where the two files simply spell the same colour differently: synonyms (order says \"Dark Blue\", 大货进度表 says \"Navy\"), abbreviations (\"Dark Brown\" vs \"DK Brown\"), and outright typos (\"Daek Blue\"). The API only ever picks among colours already on file (its answer is validated against the candidate list), so the Chinese name/code still come from the trusted 大货进度表 — a wrong pick can at worst surface the wrong existing row, never fabricate data. Only runs when Local + AI Enhance is enabled and only on a genuine miss; cached per (colour, candidate-set) so a repeated question costs one API call. **Local-only mode is unchanged — these still show 未找到** with the diagnostic comment listing 大货进度表's own colour(s)"},
            {"type": "docs", "text": "New `match_color_to_candidates()` in `color_ai_enhance.py`, tried before the existing open-ended `recognize_colors()` fallback inside `_ai_retry_component`. 10 new tests: the matcher itself (synonym pick, hallucination rejected, empty/no-candidate/error paths, caching) and end-to-end resolution of a \"(dark blue)\"→\"Navy\" mismatch through the Overview sheet"},
        ],
    },
    {
        "version": "2.15.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "Reverted the brief v2.15.0 \"客户PO + style\" lookup tier — it matched on the wrong 大货进度表 column (a separate \"PO#\" field) instead of 客人PC NO. Confirmed the correct, already-existing join key is **客人PC NO + 款式 + 英文颜色 — an exact match with no fallback tier**, which is exactly how `build_pc_style_color_lookups()` already worked before v2.15.0. No behaviour change from v2.14.1"},
        ],
    },
    {
        "version": "2.14.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**未找到 cell comments now also show 大货进度表's own colour(s) for that PC No./Style**, alongside the client's PO colour already shown — so a naming mismatch (e.g. client says \"Dark Brown\", 大货进度表 says \"Chocolate\") is visible at a glance instead of requiring the source file to be reopened. When 大货进度表 has no colour recorded at all for that PC/Style, the comment says so explicitly. When the internal DB (not 大货进度表) is the selected source, the extra line is omitted — that source was never consulted, so there's nothing to compare"},
            {"type": "docs", "text": "New shared `_color_miss_comment_text()` / `_available_progress_colors()` helpers (single source of truth for the per-style-sheet and Overview-sheet comments). 8 new tests covering both helpers directly plus end-to-end naming-mismatch and internal-DB-source cases"},
        ],
    },
    {
        "version": "2.14.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**Index sheet now includes 客人PC NO**, right after 款号 (and 图片, if photos are enabled) — mirrors the same column already added to the Overview sheet, so the PC No. used for every 大货进度表 lookup is visible without switching tabs"},
            {"type": "docs", "text": "1 new test locking in the column's presence, position, and value on the Index sheet"},
        ],
    },
    {
        "version": "2.13.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**Style hyperlinks in the buy plan (Index and Overview sheets) didn't work in WPS Office.** They were written as `cell.hyperlink = \"#'Sheet'!A1\"` — a plain string, which openpyxl always saves as an *external* relationship (`TargetMode=\"External\"`) whose literal target is that `\"#...\"` text. Excel has an undocumented leniency that follows a `\"#\"`-prefixed external target as an internal jump anyway, but that's Excel-specific, not part of the OOXML spec — WPS (and other readers) take the target literally, so the link silently did nothing. Fixed by writing the link's `location` attribute directly instead (`Hyperlink(location=\"'Sheet'!A1\", target=None)`), the spec-correct way to express a same-workbook link with no relationship at all — works the same in Excel and is now portable to WPS/LibreOffice/etc. Affects the Sky East buy plan (Index + Overview) and the HHP/Zalando buy plan Index sheet — all three shared the same pattern"},
            {"type": "docs", "text": "New shared `set_internal_hyperlink()` helper in `_excel_helpers.py` (single source of truth for all 3 call sites, was previously duplicated). 6 new tests: unit tests for the helper (location vs target, round-trips through a real save/load with zero relationships written, custom anchor, doesn't clobber an existing cell value) plus updated Index/Overview hyperlink-shape assertions"},
        ],
    },
    {
        "version": "2.13.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**找不到的颜色 (未找到) now carry a diagnostic comment showing the client's PO colour.** Every 未找到 cell in the Overview sheet and per-style sheets gets an Excel cell comment with the raw colour text exactly as the client's order file had it — before bracket-stripping or multi-colour splitting — so a reviewer can see what was actually searched for without reopening the source order file"},
            {"type": "feat", "text": "**New Sky East colour-resolution error log.** Every colour miss during buy plan generation is now recorded (PC No., Contract No., Style, PO No., client's PO colour, source) in a dedicated log — separate from the GIII PDF-parsing Exception Queue, since it's a different kind of failure. A new **Colour resolution issues** panel appears under Sky East → Contract History after generating a buy plan whenever any misses were logged, with a table and a clear-log button"},
            {"type": "docs", "text": "11 new tests: SkyEastStore.log_color_miss()/list_color_misses()/clear_color_misses() unit tests, plus end-to-end checks that a 未找到 cell gets the comment (and a resolved one doesn't), that a miss is logged with the correct raw client colour, and that passing sky_east_store=None disables logging without affecting the export itself"},
        ],
    },
    {
        "version": "2.12.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**Two-tone order-file colours now show BOTH Chinese names/codes, not just one.** A colour like \"Dark Blue / White\" used to display only whichever component happened to resolve first (e.g. \"藏青\" alone) — it now combines every component that resolves into one string, e.g. \"藏青 / 白色\" and \"52# / 3#\", matching the already-combined \"Dark Blue / White\" shown in Color (EN). A component that still can't be matched (even after AI Enhance) is silently omitted from the combination rather than blanking the whole result. \"Local + AI Enhance\" retries are now attempted per component, not just once against the full combined string, so a two-tone item with one missing colour can recover just that one"},
            {"type": "feat", "text": "**Overview sheet gains 客人PC NO and 主标颜色 columns.** 客人PC NO sits right next to Contract No. (the PC No. used for all 大货进度表 lookups, previously visible only via the underlying data, never in the sheet itself); 主标颜色 sits next to Color Code, mirroring the column that was already present on every per-style sheet but missing from the flat cross-check table"},
            {"type": "docs", "text": "6 new tests: combined-both-components resolution, label-colour passthrough when combining, AI-enhance recovering just the missing half of a two-tone pair, and end-to-end Overview checks for the combined Chinese names and the two new columns"},
        ],
    },
    {
        "version": "2.11.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**New optional \"Local + AI Enhance\" colour recognition mode.** When a Sky East order-file colour still fails to resolve locally (against the selected 大货进度表/internal-DB source) even after the multi-colour split, the DeepSeek API can now be asked to recognize the colour name(s) so a second local-lookup attempt can succeed — the API never supplies the Chinese translation or code itself, so a bad AI guess can only fail to help, never inject wrong data. The API is called **only** on a genuine colour-lookup miss, is never used for anything else (dates, quantities, other fields), and results are cached per raw colour string for the session so a repeated colour across many rows only costs one API call. Reuses the existing DeepSeek API key/model already configured for AI PO extraction — no new credential to manage"},
            {"type": "feat", "text": "New **Admin Settings → 🎨 Colour Recognition — Local + AI Enhance** toggle: **Local only** (default, no network calls) vs **Local + AI Enhance**"},
            {"type": "docs", "text": "10 new tests: `recognize_colors()` unit tests (success, cache hit, API error, malformed JSON, missing key/input) and `_resolve_pc_color_multi` AI-enhance wiring tests (disabled mode never calls the API, a local hit never calls the API, a local miss calls the API exactly once with the raw combined string, an API miss still falls back to the not-found result)"},
        ],
    },
    {
        "version": "2.10.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**Order-file multi-colour cells now use the same detect-and-separate logic as 大货进度表.** A two-tone item like `\"(dark blue)(white)\"` used to become one combined `\"Dark Blue / White\"` lookup key that could never exact-match either 大货进度表 or the internal colour DB (both store single-colour keys), silently showing 未找到/blank even when one of the two colours was mapped. The buy plan and 核料 exporters now try each colour component individually and use the first one that resolves — the combined display string is unchanged, only the lookup behaviour is smarter"},
            {"type": "docs", "text": "6 new tests covering the multi-colour resolver directly (single-colour passthrough, first-component match, second-component fallback, neither-matches) plus an end-to-end Overview-sheet check for a `\"(dark blue)(white)\"` order-file cell"},
        ],
    },
    {
        "version": "2.9.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**大货进度表 multi-colour rows are now split and independently look-up-able.** A two-tone style's colour code cell (e.g. `52#/白色 3#` for a Dark Blue/White style) used to leave the second colour's code unreachable — an order-file item coloured \"White\" could never match it. Each colour in a two-tone row now becomes its own record (same PC No./Style/contract, distinct colour), so both `get_contract_no()`/`get_color_code()`/etc. and the persisted 大货进度表 store resolve either colour correctly. When the second colour has no isolable English name (an accent/trim colour rather than a second body colour, e.g. \"BLACK WITH WHITE STRAP...\"), its Chinese name and code are still captured, just not matchable by English name alone"},
            {"type": "fix", "text": "The 色汇总 (colour summary) column was never being detected — its real header wraps onto two lines (`颜色汇总\\n英文 中文 色号 色卡本`), which didn't match any alias exactly. Header matching now collapses embedded newlines/whitespace before comparing, and the exact real-world header text was added as an alias"},
            {"type": "docs", "text": "5 new tests covering the multi-colour split (both a clean two-tone case and a headerless-accent-colour case), a normal single-colour row staying untouched, and end-to-end resolution through both `ProgressLookup` and the persisted DB store"},
        ],
    },
    {
        "version": "2.8.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "Top navigation tab renamed **📐 Fabric Mapping** → **📐 Reference Data**, since it now holds two distinct sub-sections (Style-Fabric Mapping and HHN Contract Progress) that \"Fabric Mapping\" alone no longer described. All in-app hints pointing to this tab updated to match"},
            {"type": "feat", "text": "**HHN Contract Progress** preview table now shows the Chinese colour name (中文颜色), colour code (中文颜色代码), label colour (主标颜色), ex-factory date, and quantity for every record — not just PC No. / Style / English colour / Contract No. — so a mismatch is visible directly in the preview instead of requiring a full import first"},
        ],
    },
    {
        "version": "2.8.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**Wash Label export was crashing** — `po_extractor/ui_helpers/wash_label.py` referenced `pd.NA` without ever importing pandas, so `write_wash_label_excel()` raised `NameError` any time it ran against real style data. Added the missing import; wash label generation now works"},
            {"type": "fix", "text": "Test suite cleanup: fixed 2 long-stale `test_store_factories.py` tests that assumed `fabric_master` shares `po_history.db` — it's intentionally a separate database file (`FABRIC_DB_PATH`) per the documented data/ layout, so the canonical-path test and the `fabric_in_db` fixture were both pointed at the wrong file, silently making the fixture's test data invisible to the real code path"},
            {"type": "fix", "text": "Updated 4 stale `test_excel_reports.py` PO-summary tests written against a since-replaced simple version of `generate_po_summary_excel` (a single header row + dynamic per-input-column labels). The current exporter emits a fixed title + 12-row metadata block + fixed detail-table structure; tests now assert against that actual shape. Also surfaced that the `label_for` custom-label parameter is accepted but no longer called anywhere in the current implementation — documented as a no-op rather than silently tested as if it still worked"},
            {"type": "docs", "text": "Full test suite is green for the first time this cycle: 281 passed, 0 failed (previously 13 persistent failures across three files, unrelated to any single feature change)"},
        ],
    },
    {
        "version": "2.7.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "Sky East Buy Plan sheet tab names simplified to **\"<running index>_<style>\"** (e.g. `1_DR5124`, `2_DR4578`), matching the Index sheet's own \"No.\" column — the fabric/HHN code is no longer part of the tab name. A style with multiple fabric combos still gets one sheet per combo, disambiguated purely by the index (e.g. `1_DR5009`, `2_DR5009`)"},
        ],
    },
    {
        "version": "2.7.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**大货进度表 (HHN Contract Progress)** can now be uploaded once and saved permanently, the same way **📐 Fabric Mapping** already works — no more re-uploading the same progress file for every Sky East run or buy plan. New **📋 HHN Contract Progress** sub-tab lives right next to Fabric Mapping, with the same Upsert / Add new only / Replace all import modes, a New/Will Update/Already Up to Date/Skipped preview, and a field-level diff for anything that changed (合同号, colors, codes, dates, qty, and more — every column except IMAGE). Row identity is (PC No. · Style · Color), normalised so re-uploading with different casing/whitespace still matches the same saved row instead of duplicating it"},
            {"type": "feat", "text": "Sky East order processing, the Missing Fields checker, and Buy Plan generation now automatically use the saved 大货进度表 data when no file is uploaded for that specific run — an ad-hoc upload still overrides it for a one-off test, but it's no longer required every time"},
            {"type": "refactor", "text": "Extracted `parse_progress_rows()` — the 大货进度表 column-detection and row-parsing logic — out of `ProgressLookup._load()` so both the session-upload path and the new persistent-store importer share one parser; added `ProgressLookup.from_records()` to build a lookup directly from saved DB rows with no file I/O. Behavior-preserving: all 26 existing tests pass unchanged. 20 new tests across the store, parser, and diff logic"},
        ],
    },
    {
        "version": "2.6.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "Sky East Buy Plan Chinese-colour resolution now respects the **Chinese color mapping source** radio exclusively — when 大货进度表 is selected and a style/colour isn't in it, the internal Colors DB is no longer silently tried as a fallback (even if it happens to have a matching entry). A genuine miss now shows an explicit **未找到** (\"not found\") marker in both Color (CN) and Color Code, on the per-style sheets and the Overview sheet, so a missing translation is visible rather than looking like it quietly came from a different, unselected source. A row matched in the selected source whose code field is simply blank still shows the existing `NA` placeholder — that's a different, legitimate case from a full miss. 3 new tests"},
        ],
    },
    {
        "version": "2.5.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: some order files store the colour fully wrapped in parentheses (e.g. `(dark blue)`, or two-tone as `(black)(white)`) — this showed as `(Dark Blue)` with ugly brackets in the buy plan, and worse, silently broke every colour-name lookup against 大货进度表 / the internal colour DB (which store plain names like `Dark Blue`), so the Chinese colour name and colour code came back empty even when the DB had a matching entry. Brackets are now stripped before display and lookup — `(dark blue)` → `Dark Blue`, `(black)(white)` → `Black / White` — across both the per-style sheets and the Overview sheet. Note: if Color (CN) / Color Code are still blank after this fix, the colour genuinely has no entry (or a blank one) in the selected colour source — check the 🎨 Colors tab or the loaded 大货进度表"},
        ],
    },
    {
        "version": "2.5.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "Sky East Buy Plan: new **Overview** sheet, inserted right after Index — one flat row per style/PO/colour item across the *entire* workbook, for easy cross-checking without hopping between per-style tabs. Mirrors the Contract History item-browser preview (Style with a hyperlink to its sheet, Photo, Brand, PO No., Config SKU, Article Name, sizes, Ex-Fty, Fabric N / 综合标识 Key N) plus **both English and Chinese colour names side by side and the plain colour code** as separate columns. Only created when the buy plan has at least one item. Covered by 7 new tests"},
        ],
    },
    {
        "version": "2.4.2",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**HHN Contract No. (大货进度表) lookup**: a broken formula in the source file (e.g. a 中文颜色代码 VLOOKUP with no numeric code to extract, such as \"BLACK 黑色\" with nothing after it) is cached by Excel/openpyxl as the literal text `#N/A` — not blank. This was read as a real value and leaked straight into match keys and the buy plan's 中文颜色代码 cell as garbage `#N/A` text. Excel error strings (`#N/A`, `#REF!`, `#VALUE!`, `#DIV/0!`, `#NAME?`, `#NULL!`, `#NUM!`, `#SPILL!`, `#CALC!`) are now treated as blank everywhere a progress-file cell is read, so the colour name still resolves correctly and the missing code falls back to the existing `NA` placeholder instead of the raw error"},
        ],
    },
    {
        "version": "2.4.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**HHN Contract No. (大货进度表) lookup**: `ProgressLookup` required every row to have a numeric **序号** (row sequence number) as an \"is this real data\" signal — but some 大货进度表 exports never populate that column at all. Enforcing the check unconditionally silently discarded **every row in the file**, losing 合同号 (contract no.), colours, and ex-fty dates for the whole sheet with no visible error. The gate now only applies when the file actually uses 序号 as a marker (≥1 row has a numeric value); otherwise a present style number alone is enough. Covered by 2 new tests, one confirming the original protection still holds for files that do use 序号"},
        ],
    },
    {
        "version": "2.4.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**Sky East order parsing**: a row with 0 total units (a cancelled/blanked-out order line — strikethrough style, PO and price wiped, but the row left in the sheet) is now **ignored** instead of being imported as a phantom item. Each ignored row is reported in the **Processing log** with its row number, style, and PO No., so it's visible rather than silently dropped. Covered by 3 new parser tests"},
        ],
    },
    {
        "version": "2.3.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**📐 Fabric Mapping** import preview: **♻️ Will update** was flagged for any style already in the database, even when its content matched the file exactly (e.g. after a duplicate combo had already been cleaned up) — misleading, since nothing would actually change. Existing styles are now diffed up front and split into **♻️ Will update** (real content difference) vs. a new **✓ Already up to date** count; the style list and the differences expander reflect the same split"},
        ],
    },
    {
        "version": "2.3.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**📐 Fabric Mapping** tab: new **🩺 Check for duplicate fabric mapping data** section — scans all companies for a style whose fabric combo is stored identically twice under different combo numbers, and a one-click **🧹 Remove all duplicate combos** button to clean them up (only the extra copy is removed; the kept combo is untouched). Backed by two new store methods, `find_duplicate_fabric_combos()` and `delete_fabric_combo()`, covered by 7 new tests"},
            {"type": "fix", "text": "Cleaned up 2 real duplicate-combo styles found in the live database (**BL3069**, **ZLD060/S24DTR003**) — each was stored twice with byte-for-byte identical fabric data, which would have produced an extra duplicate sheet per style in the next Sky East Buy Plan export"},
        ],
    },
    {
        "version": "2.2.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**📐 Fabric Mapping** diff (added in 2.2.0): a stored fabric slot missing from the uploaded file was always labeled **(slot removed)** — but `save_fabric_parts_batch()` only upserts, it never deletes, so under **Upsert** / **Add new only** that slot actually stays in the database untouched. The label now depends on the selected import mode: **(slot removed)** only under **Replace all** (which does wipe first); otherwise **(not in file — kept, not deleted)** with a note explaining Replace all is needed to actually remove it. Styles under **Add new only** now show a plain skip notice instead of a diff, since existing styles aren't touched at all in that mode"},
        ],
    },
    {
        "version": "2.2.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**📐 Fabric Mapping** import preview: styles flagged **♻️ Will update** now have a field-level diff against the currently stored data — shows Stored vs. In File for each changed Body Part / HHN No. / Composition / Weight / Width, plus added or removed fabric slots. Styles whose file content is identical to what's stored are called out separately, so a 'Will update' count no longer means a guaranteed change"},
            {"type": "fix", "text": "Sky East upload page: the fabric-mapping hint pointed at a stale location (**Contract History → 🧵 Fabric Mapping**) that no longer matches the app's tab layout — corrected to the actual top-level **📐 Fabric Mapping** tab"},
        ],
    },
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
