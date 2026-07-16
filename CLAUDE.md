# PO Automation GIII — Claude Code Instructions

## HARD RULES (no exceptions)

### 1. Bump APP_VERSION after every code change
- Open `app.py` and increment `APP_VERSION = "x.y.z"` **as part of the same edit session** in which any file is modified.
- Do NOT wait until the end of the conversation. Bump it immediately after each change.
- Versioning convention:
  - Patch (x.y.**Z**) → bug fix, small tweak, docs, config
  - Minor (x.**Y**.0) → new feature, new tab, new module
  - Major (**X**.0.0) → architectural change, breaking schema change

### 2. Commit every meaningful change to git
- After completing a task (or a logical group of related changes), create a git commit.
- Commit message format: `type: short description (vX.Y.Z)`
  - Types: `feat`, `fix`, `perf`, `refactor`, `docs`, `chore`
  - Examples:
    - `fix: Sky East Buy Plan multiselect desync (v2.0.3)`
    - `perf: wrap tabs in st.fragment + WAL-once fix (v2.0.6)`
    - `feat: add Production Stage Tracking module (v1.15.0)`
- Stage only relevant source files — never commit `.env`, secrets, or large binaries.
- Always commit **before** starting the next unrelated task.

### 3. Update the in-app changelog
- After bumping APP_VERSION, add a matching entry to `_CHANGELOG` in `ui/changelog_view.py`.
- Insert at the **top** of the list (newest first).
- Required fields: `version`, `date` (ISO format, today's date), `entries` (list of `{type, text}`).
- Types mirror commit types: `feat`, `fix`, `perf`, `refactor`, `security`, `docs`.

### 4. Restart the server after module-level changes
- `app.py` changes are hot-reloaded by Streamlit automatically.
- Changes to **imported modules** (anything under `po_extractor/`, `ui/`) require a server restart to take effect. Stop and restart `streamlit run app.py --server.headless true`.

## Project context

- **App entry point:** `app.py` — `APP_VERSION` is near the top.
- **Changelog:** `ui/changelog_view.py` — `_CHANGELOG` list, newest first.
- **Python interpreter:** `C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe`
  (the default `python` on PATH is 3.14 and does **not** have the app's deps — always use the 3.13 path above).
- **Start server:** `streamlit run app.py --server.headless true > streamlit_run.log 2>&1` (background)
- **Server health check:** `curl http://localhost:8501/_stcore/health`
- **Rollback snapshot:** `requirements.lock` (78 packages, exact versions as of 2026-06-18).
  Roll back with `python -m pip install -r requirements.lock`.
- **Deep architecture reference:** `IMPLEMENTATION_GUIDE.md` (data models, PDF/Excel pipelines, exporters, column mapping). Read it before large changes; don't duplicate it here.
- **Building a distributable install pack** (to set the app up on a different PC): `installer/Build-DistPackage.bat` (dev machine only) — exports the tracked tree via `git archive`, flattens `installer/*` up to the pack root (`Install.ps1`/`Update.ps1`/`Uninstall.ps1` all assume they're siblings of `app.py`/`requirements.lock`, not nested a folder down), and zips the result into `dist/` (gitignored). The target PC just needs internet access to run the resulting `Install.bat`.

## Layout (where things live)

- `po_extractor/` — backend, no Streamlit. `parsers/` (PDF + Excel → records), `detectors/` (file-type detection), `exporters/` (buy plan / Template_P / 核料 / wash label), `lookups/` (fabric, color, progress), `store/` (SQLite), `models/`, `utils/`.
- `ui/` — Streamlit views, one sub-package per tab (`giii/`, `sky_east/`, `fabric_db/`). Tab wrappers live in `app.py`.
- `data/` — runtime SQLite DBs (`po_history.db`, `fabric_master.db`) + generated output. **gitignored** — never commit.
- `auth/` — `users.json` (bcrypt hashes from `setup_users.py`). **Never commit.**
- `tests/` — pytest (20 files). `docs/` — generated docs & screenshots.

## Conventions (follow these when editing)

- **Stores go through factories, never direct construction.**
  - `po_extractor/store/__init__.py` = canonical, non-Streamlit factories (`get_po_store()`, `get_sky_east_store()`, …).
  - `ui/stores.py` is the **only** place `@st.cache_resource` may appear — every Streamlit caller imports from there. (A past class of silent-failure bugs came from duplicate factory paths; don't reintroduce them.)
  - All stores subclass `BaseSQLiteStore` and open connections via `self._conn()`.
- **DB paths come from `po_extractor/config.py`** (`DB_PATH`, `FABRIC_DB_PATH` — the latter honors the `FABRIC_DB_PATH` env var). Never hardcode `data/*.db`.
- **Session state uses the `SK` constants** from `ui/session_keys.py` — never raw `st.session_state["literal"]` strings. Add a new `SK.*` constant when you need a new key.
- **All user-facing text is translated.** Wrap strings in `t()` (`ui/i18n.py`); for DataFrame column headers use `_th("Header")` and for rename maps `_tr({...})` (`ui/shared.py`). Literal column names break under the Chinese UI.
- **CPRS is the single source of truth — never build a local gate on it.** All GIII requirement values (red sticker, carton mark, prepack ratio, pcs/carton, carton weight, MSRP/RFID, and the decoded warehouse/account/channel/COO) come from one `cprs.evaluate_po(rawPO)` call and are rendered verbatim, status-aware. Do **not** add app-side applicability gates (no "prepack-only", no "warehouse == X"), derivation, or business rules on top — CPRS's own status decides. Full rationale: `docs/GIII_CPRS_Integration_API.md` ("Design principle").

## Streamlit gotchas (cost real debugging time before)

- **Tabs are wrapped in `st.fragment`** (in `app.py`) so a widget interaction reruns only its own tab. Keep new tabs consistent. Explicit `st.rerun()` stays app-scoped by default.
- **Multiselect desync:** with `key=` set, do **not** also pass `default=`. Before each multiselect, run the stale-value guard (drop selected values no longer in `options`) or deletes/reruns crash with `StreamlitAPIException`.
- **Imported-module edits need a server restart** (Streamlit only hot-reloads `app.py`). See rule 4.

## Testing & pre-commit

- Run the suite before committing: `C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe -m pytest tests/ -q`
- `tests/test_app_imports.py` and `tests/test_store_factories.py` catch most wiring breakage cheaply — run at least these after refactors.

## Never commit

`.env`, `.streamlit/secrets.toml`, `auth/users.json`, the `data/*.db` files, or sample PO PDFs/Excel at the repo root. `.gitignore` already covers these — keep it that way and stage files explicitly (`git add <path>`), never `git add -A` blindly.
