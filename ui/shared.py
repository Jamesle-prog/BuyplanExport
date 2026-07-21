"""Shared Streamlit utilities used across multiple view modules.

All helpers in this module are safe to import without a running Streamlit
server -- they only call Streamlit APIs inside functions, never at module
import time.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import streamlit as st

from ui.session_keys import SK as _SK

from ui.stores import IMAGES_DIR_DEFAULT

# Persistent fallback folder for images extracted from source spreadsheets.
# Processing saves every extracted image here (in addition to the user's
# configured image folder), so a later buy-plan run can still find them after a
# restart clears the in-memory cache, or when the configured folder was changed
# or emptied.  Image lookups fall back to this folder when the primary misses.
EXTRACTED_IMAGES_DIR = os.path.join(os.path.dirname(IMAGES_DIR_DEFAULT), "extracted_images")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV_MIME  = "text/csv"
ZIP_MIME  = "application/zip"

# File-type lists for st.file_uploader — single source of truth so changes
# (e.g. allowing .xlsm in legacy uploaders) only need one edit.
EXCEL_FILE_TYPES            = ["xlsx", "xls"]
EXCEL_FILE_TYPES_WITH_MACRO = ["xlsx", "xls", "xlsm"]
DEFAULT_XLSX_EXT            = ".xlsx"

# ---------------------------------------------------------------------------
# Language / label translation
# ---------------------------------------------------------------------------

_LABEL_ZH: dict[str, str] = {
    # Shared
    "Company":                   "公司",
    "Companies":                 "公司数",
    "Source":                    "来源",
    "POs":                       "订单数",
    "Total POs":                 "总订单数",
    "Styles":                    "款式数",
    "Total Styles":              "总款式数",
    "Units":                     "数量",
    "Total Units":               "总数量",
    "Total Qty":                 "总数量",
    "Factory":                   "工厂",
    "COO":                       "原产地",
    "Latest Ex-Fty":             "最新离厂日期",
    "Ex-Fty":                    "离厂日期",
    "Ex-Fty Date":               "离厂日期",
    "PC No.":                    "合同编号",
    "PO No.":                    "采购单号",
    "Style":                     "款式",
    "Style No.":                 "款式编号",
    "Color":                     "颜色",
    "Brand":                     "品牌",
    "Photo":                     "图片",
    "Source File":               "来源文件",
    "Extracted At":              "提取时间",
    # Sky East items
    "HHN Contract No.":          "HHN合同号",
    "Config SKU":                "Config SKU",
    "Article Name":              "商品名称",
    "Color Code":                "颜色代码",
    "Fabric No.":                "面料编号",
    "Composition":               "成分",
    "Cuttable Width (cm)":       "有效门幅(cm)",
    "Fabric Key":                "综合标识Key",
    "Shrinkage Rate":            "烫缩率",
    "Short Rate":                "短码率",
    # Sky East contracts
    "PC Date":                   "合同日期",
    "Buyer":                     "买方",
    "Seller":                    "卖方",
    "Currency":                  "币种",
    "Trade Term":                "贸易条款",
    # GIII / history
    "Division":                  "分部",
    "Issue Date":                "下单日期",
    "Version":                   "版本",
    "File":                      "文件",
    # Missing fields
    "Fabric No. (was)":          "面料编号(原)",
    "HHN Contract No. (was)":    "HHN合同号(原)",
    "Fabric No. → (new)":        "面料编号→(新)",
    "HHN Contract No. → (new)":  "HHN合同号→(新)",
}


def _th(label: str) -> str:
    """Translate a header label to the active UI language.

    Lookup order:
    1. DB-backed ``t()`` (UITranslationStore) — live, editable via Admin.
    2. Hardcoded ``_LABEL_ZH`` dict — compile-time fallback for robustness.
    3. Original English label — when no translation exists anywhere.
    """
    if st.session_state.get(_SK.UI_LANG) != "zh":
        return label
    try:
        from ui.i18n import t as _t
        translated = _t(label)
        if translated != label:
            return translated
    except Exception:
        pass
    return _LABEL_ZH.get(label, label)


def _tr(mapping: dict) -> dict:
    """Apply _th() to all values in a rename dict."""
    return {k: _th(v) for k, v in mapping.items()}


# ---------------------------------------------------------------------------
# Processing-log expander
# ---------------------------------------------------------------------------

_LOG_ISSUE_MARKERS = ("⚠", "❌", "error", "warning", "failed")


def show_processing_log(lines, *, title: str = "Processing log") -> None:
    """Render a processing-log expander that can't hide failures.

    Collapsed with a plain label when the log is clean; auto-expanded with the
    issue count in the label (e.g. "Processing log (2 ⚠️)") when any line
    carries an error/warning marker — a run with problems must not look
    identical to a clean one.
    """
    if not lines:
        return
    from ui.i18n import t as _t
    n_issues = sum(
        1 for line in lines
        if any(m in str(line).lower() for m in _LOG_ISSUE_MARKERS)
    )
    label = f"{_t(title)} ({n_issues} ⚠️)" if n_issues else _t(title)
    with st.expander(label, expanded=bool(n_issues)):
        for line in lines:
            st.markdown(line, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Progress tracker
# ---------------------------------------------------------------------------

class ProgressTracker:
    """Inline progress bar + elapsed / ETA timer for Streamlit status blocks."""

    def __init__(self, total: int):
        self.total   = max(total, 1)
        self.current = 0
        self.start   = time.time()
        self._bar    = st.progress(0.0)
        self._txt    = st.empty()
        self._refresh()

    def step(self, label: str = "") -> None:
        self.current = min(self.current + 1, self.total)
        self._refresh(label)

    def done(self) -> None:
        self.current = self.total
        self._bar.progress(1.0)
        elapsed = time.time() - self.start
        m, s = divmod(int(elapsed), 60)
        self._txt.caption(f"Completed in {m}:{s:02d}")

    def _refresh(self, label: str = "") -> None:
        frac    = self.current / self.total
        elapsed = time.time() - self.start
        m_e, s_e = divmod(int(elapsed), 60)
        elapsed_str = f"{m_e}:{s_e:02d}"

        if frac > 0.05 and self.current < self.total:
            remaining = elapsed / frac * (1 - frac)
            m_r, s_r  = divmod(int(remaining), 60)
            eta_str   = f" · ~{m_r}:{s_r:02d} remaining"
        else:
            eta_str = ""

        step_str = f"Step {self.current}/{self.total}" if self.current else "Starting..."
        detail   = f" -- {label}" if label else ""
        self._bar.progress(min(frac, 1.0))
        self._txt.caption(f"{step_str}{detail}  ·  {elapsed_str} elapsed{eta_str}")


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def fragment_rerun() -> None:
    """Rerun only the enclosing ``@st.fragment`` (the current tab), falling
    back to a full-app rerun when called outside a fragment.

    Perf: a plain ``st.rerun()`` from inside a tab fragment is APP-scoped --
    it re-executes every tab body plus the sidebar and re-mounts the whole
    page in the browser, so each save/import/delete paid the full-app cost.
    Use this for actions whose effects are contained in the current tab.
    Keep plain ``st.rerun()`` for actions other tabs passively display
    (e.g. PO uploads feeding the Summary tab) -- with client-side tab
    switching, a fragment-scoped rerun would leave those views stale.

    The except clause is safe: ``st.rerun`` raises ``StreamlitAPIException``
    at CALL time when no fragment is active; the ``RerunException`` it
    raises as control flow on success is a sibling class and propagates.
    """
    from streamlit.errors import StreamlitAPIException
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def guard_multiselect_state(key: str, options) -> None:
    """Drop stale values from a multiselect's session state before rendering.

    Values no longer present in *options* (e.g. after a delete + rerun, or a
    filter change) historically raised ``StreamlitAPIException``; Streamlit
    1.58 instead silently clears the WHOLE selection.  Pruning just the stale
    values keeps the rest of the user's selection.  Run this before every
    multiselect whose options are DB-derived (CLAUDE.md convention).
    """
    opts = set(options)
    cur = st.session_state.get(key)
    if isinstance(cur, list) and any(v not in opts for v in cur):
        st.session_state[key] = [v for v in cur if v in opts]


def persisted_download(
    state_key: str,
    *,
    default_fname: str = "download",
    default_mime: str = "application/octet-stream",
    fixed_mime: str | None = None,
    label: str | None = None,
    use_container_width: bool = False,
    key_suffix: str = "btn",
) -> None:
    """Render a st.download_button for bytes persisted in session_state.

    Conventional keys (all read from st.session_state):
      * {state_key}_bytes -- payload (required; if missing/falsy, renders nothing)
      * {state_key}_fname -- filename (optional)
      * {state_key}_mime  -- MIME type (optional; overridden by fixed_mime)
    """
    data = st.session_state.get(f"{state_key}_bytes")
    if not data:
        return
    fname = st.session_state.get(f"{state_key}_fname") or default_fname
    mime  = fixed_mime or st.session_state.get(f"{state_key}_mime") or default_mime
    st.download_button(
        label=(label or f"Download {fname}"),
        data=data,
        file_name=fname,
        mime=mime,
        use_container_width=use_container_width,
        key=f"{state_key}_{key_suffix}",
    )


# ---------------------------------------------------------------------------
# Image folder expander widget
# ---------------------------------------------------------------------------

_HISTORY_FILE = Path(__file__).parent.parent / "data" / "image_folder_history.json"
_HISTORY_MAX  = 20   # max entries kept per session_key


def _load_history(session_key: str) -> list[str]:
    """Load persisted folder history for *session_key* from disk."""
    try:
        data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        return [p for p in data.get(session_key, []) if isinstance(p, str) and p]
    except Exception:
        return []


def _save_history(session_key: str, history: list[str]) -> None:
    """Write *history* for *session_key* back to disk."""
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if _HISTORY_FILE.exists():
            try:
                existing = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing[session_key] = history[:_HISTORY_MAX]
        _HISTORY_FILE.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _push_history(session_key: str, path: str) -> list[str]:
    """Add *path* to the front of the history list (dedup, persist, return new list)."""
    history = _load_history(session_key)
    history = [p for p in history if p != path]  # remove duplicate
    history.insert(0, path)
    _save_history(session_key, history)
    return history


def show_image_folder_expander(session_key: str, apply_key: str) -> None:
    """Render the Image folder expander with persistent history dropdown."""
    try:
        from ui.i18n import t as _t
    except Exception:
        def _t(s: str) -> str:  # type: ignore[misc]
            return s

    # ------------------------------------------------------------------
    # Bootstrap: on first render, seed session state from persisted history
    # ------------------------------------------------------------------
    hist_key    = f"{session_key}_history"
    if hist_key not in st.session_state:
        st.session_state[hist_key] = _load_history(session_key)
    # Also seed the active folder from history if not already set
    if not st.session_state.get(session_key) and st.session_state[hist_key]:
        st.session_state[session_key] = st.session_state[hist_key][0]

    history: list[str] = st.session_state[hist_key]

    with st.expander(_t("Image folder (load & save style photos)")):
        st.caption(
            "Images are loaded from and saved here as `{style}_front.png` / `{style}_back.png` "
            "and also as `{picture_id}.png` for internal lookup. "
            "Leave blank to use the built-in default folder."
        )

        # ------------------------------------------------------------------
        # History dropdown (only shown when there is history)
        # ------------------------------------------------------------------
        if history:
            CLEAR_LABEL = "— Clear history —"
            options = history + [CLEAR_LABEL]
            chosen = st.selectbox(
                _t("Recent folders"),
                options=options,
                index=0,
                key=f"{session_key}_selectbox",
            )
            if chosen == CLEAR_LABEL:
                st.session_state[hist_key] = []
                _save_history(session_key, [])
                fragment_rerun()
            else:
                # Selecting from dropdown pre-fills the text input
                prefill = chosen
        else:
            prefill = st.session_state.get(session_key, "")

        # ------------------------------------------------------------------
        # Manual text input
        # ------------------------------------------------------------------
        img_dir_input = st.text_input(
            _t("Folder path"),
            value=prefill,
            placeholder=IMAGES_DIR_DEFAULT,
            key=f"{session_key}_input",
        )

        c1, c2 = st.columns([2, 1])
        with c1:
            if img_dir_input.strip():
                exists = os.path.isdir(img_dir_input.strip())
                st.caption(
                    _t("Folder exists") if exists
                    else _t("Folder not found — it will be created when processing runs.")
                )
        with c2:
            if st.button(_t("Apply"), key=apply_key):
                new_path = img_dir_input.strip()
                st.session_state[session_key] = new_path
                if new_path:
                    updated = _push_history(session_key, new_path)
                    st.session_state[hist_key] = updated
                st.success(_t("Image folder updated."))


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def images_dir(session_key: str = "se_images_dir") -> str:
    """Return the configured image folder path (falls back to default)."""
    d = (st.session_state.get(session_key) or "").strip()
    return d if d else IMAGES_DIR_DEFAULT


def load_photo_map_from_dir(folder: str) -> dict[str, bytes]:
    """Load all image files from folder into a filename->bytes dict."""
    photo_map: dict[str, bytes] = {}
    if not folder or not os.path.isdir(folder):
        return photo_map
    for fname in os.listdir(folder):
        if fname.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff")):
            try:
                with open(os.path.join(folder, fname), "rb") as fh:
                    photo_map[fname] = fh.read()
            except Exception:
                pass
    return photo_map


def load_image(picture_id: str,
               session_cache_key: str = "se_image_cache",
               img_dir: str | None = None) -> bytes | None:
    """Return image bytes: session cache first, then disk (by picture_id)."""
    if not picture_id:
        return None
    cache = st.session_state.get(session_cache_key) or {}
    if picture_id in cache:
        return cache[picture_id]
    primary = img_dir if img_dir is not None else images_dir()
    # Primary (configured) folder first, then the persistent extracted-images
    # fallback so images survive restarts / a changed image folder.
    for folder in (primary, EXTRACTED_IMAGES_DIR):
        path = os.path.join(folder, f"{picture_id}.png")
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return f.read()
            except OSError:
                pass
    return None


def load_style_photo_pair(style: str, primary_dir: str | None = None) -> list:
    """Return ``[front_bytes|None, back_bytes|None]`` for *style*.

    Looks in the primary (configured) folder first, then the persistent
    :data:`EXTRACTED_IMAGES_DIR` fallback, for ``{safe_style}_front.png`` /
    ``{safe_style}_back.png``.  Used by the buy-plan generator so photos still
    embed after a restart or a changed image folder.
    """
    import re as _re
    safe = _re.sub(r'[\\/:*?"<>|]', '_', str(style or ""))
    primary = primary_dir if primary_dir is not None else images_dir()
    pair: list = []
    for pos in ("front", "back"):
        data = None
        for folder in (primary, EXTRACTED_IMAGES_DIR):
            p = os.path.join(folder, f"{safe}_{pos}.png")
            if os.path.exists(p):
                try:
                    with open(p, "rb") as fh:
                        data = fh.read()
                    break
                except OSError:
                    pass
        pair.append(data)
    return pair


# Local mirror of photo bytes read from an EXTERNAL (often network-mounted)
# image folder. Filenames encode source size+mtime, so a changed source file
# simply misses the cache — no invalidation logic, no staleness window.
PHOTO_CACHE_DIR = os.path.join(os.path.dirname(IMAGES_DIR_DEFAULT), "photo_cache")


def _is_app_local_dir(folder: str) -> bool:
    """True when *folder* lives under the app's own data dir (already local,
    so mirroring its bytes into the cache would be pure waste)."""
    try:
        root = os.path.abspath(os.path.dirname(IMAGES_DIR_DEFAULT))
        return os.path.commonpath([root, os.path.abspath(folder)]) == root
    except (OSError, ValueError):
        return False


# How long a broken source photo is skipped before being retried. A corrupt
# file on a network mount can HANG for the mount's full timeout (measured:
# one bad PNG on a Mountain Duck share stalled 60.5s then failed EINVAL --
# every single generation, since a failed read never enters the byte cache).
_BAD_PHOTO_RETRY_SECONDS = 6 * 3600

# Files skipped by the most recent load_style_photo_map call (full paths) --
# surfaced by the UI so the user knows exactly which file to fix on the share.
_last_photo_errors: list[str] = []


def get_last_photo_errors() -> list[str]:
    """Source photos the last :func:`load_style_photo_map` call could not
    read (broken/hanging files, skipped via the bad-file marker)."""
    return list(_last_photo_errors)


def _read_photo_cached(folder: str, fname: str,
                       cached_names: set[str] | None = None,
                       errors: list | None = None) -> bytes | None:
    """Read ``folder/fname``, mirroring it locally so later runs skip the
    network. Stats the SOURCE file (one metadata round-trip) to build a
    size+mtime cache key — a source edit yields a different key (miss →
    re-read), so the cache can never serve stale bytes. *cached_names* is an
    optional pre-fetched listing of PHOTO_CACHE_DIR so the hit check is a
    set lookup instead of a filesystem probe. Failures are non-fatal.

    A file whose stat/read FAILS gets a local ``.bad`` marker and is skipped
    without touching the source for ``_BAD_PHOTO_RETRY_SECONDS`` — one
    corrupt file on a network mount otherwise stalls the mount's full
    timeout on EVERY run. A later successful read clears the marker.
    """
    import hashlib
    import time as _t
    key = hashlib.sha1(f"{folder}|{fname}".encode("utf-8", "replace")).hexdigest()[:16]

    bad_marker = os.path.join(PHOTO_CACHE_DIR, f"{key}.bad")
    _marker_known = cached_names is None or f"{key}.bad" in cached_names
    if _marker_known:
        try:
            if _t.time() - os.path.getmtime(bad_marker) < _BAD_PHOTO_RETRY_SECONDS:
                if errors is not None:
                    errors.append(os.path.join(folder, fname))
                return None            # known-bad, retry window not elapsed
        except OSError:
            pass                       # no marker -> proceed normally

    def _mark_bad() -> None:
        try:
            os.makedirs(PHOTO_CACHE_DIR, exist_ok=True)
            with open(bad_marker, "w") as fh:
                fh.write(fname)
        except OSError:
            pass
        if errors is not None:
            errors.append(os.path.join(folder, fname))

    try:
        st_ = os.stat(os.path.join(folder, fname))
    except OSError:
        _mark_bad()
        return None
    cache_name = f"{key}_{st_.st_size}_{int(st_.st_mtime)}.bin"
    cache_path = os.path.join(PHOTO_CACHE_DIR, cache_name)
    if cached_names is None or cache_name in cached_names:
        try:
            with open(cache_path, "rb") as fh:
                return fh.read()                  # hit — no network content read
        except OSError:
            pass
    try:
        with open(os.path.join(folder, fname), "rb") as fh:
            data = fh.read()                      # miss — pay the source read
    except OSError:
        _mark_bad()
        return None
    try:
        os.makedirs(PHOTO_CACHE_DIR, exist_ok=True)
        # Drop superseded versions of this same source file + any bad marker.
        for old in os.listdir(PHOTO_CACHE_DIR):
            if old.startswith(key + "_") or old == f"{key}.bad":
                try:
                    os.remove(os.path.join(PHOTO_CACHE_DIR, old))
                except OSError:
                    pass
        with open(cache_path, "wb") as fh:
            fh.write(data)
    except OSError:
        pass
    return data


def load_style_photo_map(styles, primary_dir: str | None = None) -> dict[str, list]:
    """Batch version of :func:`load_style_photo_pair` for many styles at once:
    ``{style: [front_bytes|None, back_bytes|None]}`` (styles with no photo at
    all are omitted).

    Built for network-mounted image folders (Mountain Duck / SMB), where
    naive approaches were minutes-slow. Hard-won rules, each measured on a
    real Mountain Duck mount:

    1. Enumerate NAMES ONLY (``os.listdir``, one call, ~0s for 384 files).
       Never stat the whole folder — per-entry stat on the mount was ~150ms
       × every file in the folder (60s), swamping everything else.
    2. Stat/read ONLY the wanted files (≤ 2 per style), CONCURRENTLY —
       mount latency dominates per-file cost, so 12 workers ≈ 12× faster.
    3. Bytes from an external folder are mirrored into a local cache keyed
       by size+mtime; warm runs cost one parallel stat per wanted file plus
       local reads — no content ever crosses the network twice.

    A folder that cannot be listed contributes nothing (one fast failure
    instead of a hang per file).
    """
    import re as _re
    from concurrent.futures import ThreadPoolExecutor

    primary = primary_dir if primary_dir is not None else images_dir()
    listings: list[tuple[str, set[str]]] = []
    for folder in (primary, EXTRACTED_IMAGES_DIR):
        try:
            listings.append((folder, set(os.listdir(folder))))
        except OSError:
            listings.append((folder, set()))

    # Resolve which (folder, filename) each style/position should read from.
    wanted: list[tuple[str, int, str, str]] = []
    for style in styles:
        s = str(style or "").strip()
        if not s:
            continue
        safe = _re.sub(r'[\\/:*?"<>|]', '_', s)
        for idx, pos in enumerate(("front", "back")):
            fname = f"{safe}_{pos}.png"
            for folder, names in listings:
                if fname in names:
                    wanted.append((s, idx, folder, fname))
                    break

    if not wanted:
        return {}

    try:
        cached_names = set(os.listdir(PHOTO_CACHE_DIR))
    except OSError:
        cached_names = set()

    _last_photo_errors.clear()
    _errors = _last_photo_errors

    def _fetch(job):
        _s, _idx, folder, fname = job
        if _is_app_local_dir(folder):
            try:
                with open(os.path.join(folder, fname), "rb") as fh:
                    return _s, _idx, fh.read()
            except OSError:
                return _s, _idx, None
        return _s, _idx, _read_photo_cached(folder, fname, cached_names, _errors)

    out: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=min(12, len(wanted))) as ex:
        for _s, _idx, data in ex.map(_fetch, wanted):
            if data is None:
                continue
            out.setdefault(_s, [None, None])[_idx] = data
    return out


def save_images_to_disk(image_dict: dict,
                        style_pid_map: dict[str, list[str]] | None = None,
                        img_dir: str | None = None) -> None:
    """Persist images to the configured folder.

    Saves two forms:
      {picture_id}.png          -- internal key used for DB lookups
      {style}_front.png / {style}_back.png -- human-readable front/back copies

    Best-effort: photo embedding is a secondary feature layered on top of
    the real PO/contract data (already saved to the DB by the time this
    runs). A misconfigured or unreachable folder -- e.g. a network path
    from a different machine/office that this install can't authenticate
    to (WinError 1326) -- must not crash the whole upload; warn and return
    instead so the caller's fallback save (EXTRACTED_IMAGES_DIR) still runs.
    """
    import re as _re
    folder = img_dir if img_dir is not None else images_dir()
    try:
        os.makedirs(folder, exist_ok=True)

        for pid, data in image_dict.items():
            if pid and data:
                path = os.path.join(folder, f"{pid}.png")
                if not os.path.exists(path):
                    with open(path, "wb") as f:
                        f.write(data)

        if style_pid_map:
            for style, pids in style_pid_map.items():
                safe_style = _re.sub(r'[\\/:*?"<>|]', '_', style)
                for i, pid in enumerate(pids[:2]):
                    position = "front" if i == 0 else "back"
                    img_bytes = image_dict.get(pid)
                    if img_bytes:
                        fname = os.path.join(folder, f"{safe_style}_{position}.png")
                        with open(fname, "wb") as f:
                            f.write(img_bytes)
    except OSError as exc:
        st.warning(
            f"⚠️ Could not save images to '{folder}' ({exc}). "
            "Photos will still be found via the local extracted-images fallback; "
            "check the configured image folder in Admin Settings if this persists."
        )


def build_image_cache_for_ids(picture_ids,
                              session_cache_key: str = "se_image_cache",
                              img_dir: str | None = None) -> dict:
    """Return {picture_id: bytes} for the given IDs, loading from session then disk.

    Already-loaded images are served from the session-state cache so repeated
    Generate presses skip all disk I/O for images that were loaded previously.
    Newly loaded images are written back into the session cache so future calls
    (within the same session) are instant.
    """
    session_cache: dict = st.session_state.setdefault(session_cache_key, {})
    result: dict = {}
    for pid in picture_ids:
        pid = str(pid).strip() if pid else ""
        if not pid:
            continue
        if pid in session_cache:
            # Already in session — free hit
            result[pid] = session_cache[pid]
            continue
        # Not cached yet — try the configured folder, then the persistent
        # extracted-images fallback; populate the session cache on a hit.
        primary = img_dir if img_dir is not None else images_dir()
        for folder in (primary, EXTRACTED_IMAGES_DIR):
            path = os.path.join(folder, f"{pid}.png")
            if os.path.exists(path):
                try:
                    with open(path, "rb") as _f:
                        b = _f.read()
                    session_cache[pid] = b
                    result[pid] = b
                    break
                except OSError:
                    pass
    return result
