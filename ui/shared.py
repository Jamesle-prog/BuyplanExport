"""Shared Streamlit utilities used across multiple view modules.

All helpers in this module are safe to import without a running Streamlit
server -- they only call Streamlit APIs inside functions, never at module
import time.
"""
from __future__ import annotations

import base64
import io
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

# MIME types — canonical values live in po_extractor.config; re-exported here
# so the many `from ui.shared import XLSX_MIME` call sites keep working.
from po_extractor.config import XLSX_MIME, ZIP_MIME, CSV_MIME, HTML_MIME  # noqa: F401


# ---------------------------------------------------------------------------
# CSV export hygiene
# ---------------------------------------------------------------------------
def csv_safe(df):
    """Return a copy of *df* safe to write with ``.to_csv(...)`` for download.

    Defuses spreadsheet-formula injection: a cell whose text starts with
    ``= + - @`` (or tab/CR) is evaluated when Excel/LibreOffice opens the CSV,
    so a payload carried in the data would run on whoever opens the file. This
    is the CSV counterpart to the xlsx exporters' ``neutralise_foreign_formulas``.

    Thin wrapper over the canonical backend helper so there is one implementation;
    imported lazily to keep this module import-light and cycle-free.
    """
    from po_extractor.exporters._excel_helpers import neutralise_csv_frame
    return neutralise_csv_frame(df)

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
        from ui.i18n import t as _t
        self._txt.caption(_t("Completed in {m}:{s}").format(m=m, s=f"{s:02d}"))

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
        from ui.i18n import t as _t
        self._txt.caption(f"{step_str}{detail}  ·  {elapsed_str} {_t('elapsed')}{eta_str}")


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


def lazy_sections(sections: list[tuple], key: str) -> None:
    """Render ONE of *sections* — a tab bar that doesn't build what it hides.

    ``sections`` is ``[(label, render_fn), ...]``; only the selected entry's
    function is called.

    Use this instead of ``st.tabs`` for anything whose panels do real work.
    ``st.tabs`` executes **every** tab body on **every** script run — wrapping
    a tab in ``@st.fragment`` does not change that, a fragment only narrows
    reruns triggered from inside it. Screens with four data-loading panels were
    therefore doing four panels' work to show one.

    Selection is held in session state under *key* so it survives the reruns
    that buttons inside a panel trigger — with ``st.tabs`` those reruns snapped
    the user back to the first tab, which made freshly created download buttons
    look like they had never appeared.

    Labels are translated and the language toggle changes them, so a stored
    value that is no longer an option is dropped rather than allowed to raise.
    """
    from ui.i18n import t as _t

    labels = [lbl for lbl, _ in sections]
    if not labels:
        return
    if st.session_state.get(key) not in labels:
        st.session_state[key] = labels[0]
    # A real label even though it is collapsed: Streamlit 1.62 warns on an
    # empty one (it is what a screen reader announces), and this helper is
    # called several times per render, so the log filled up with the warning.
    active = st.segmented_control(
        _t("Section"), labels, key=key, label_visibility="collapsed")
    if active not in labels:            # deselected — keep showing something
        active = st.session_state[key]
    sections[labels.index(active)][1]()


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
    width: str = "content",
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
        width=width,
        key=f"{state_key}_{key_suffix}",
    )


# ---------------------------------------------------------------------------
# One-shot flash messages
# ---------------------------------------------------------------------------

_FLASH_KINDS = ("success", "info", "warning", "error")


def set_flash(key: str, message: str, kind: str = "success") -> None:
    """Queue a one-shot message to show after the rerun an action triggers.

    Pair with :func:`show_flash` at the top of the view.  The canonical shape
    is a ``(kind, message)`` tuple; ``show_flash`` also accepts the older
    plain-string and dict shapes so no producer is forced to change.
    """
    st.session_state[key] = (kind, message)


def show_flash(key: str, *, default_kind: str = "success"):
    """Pop and render the one-shot message stored under *key*.

    Six views used to hand-roll this in three different shapes.  Accepted:

    * ``(kind, message)`` — the canonical tuple (``set_flash`` writes this).
    * ``"message"``       — rendered as *default_kind*, or as an error when
      it starts with ``❌`` (the mailbox-check convention).
    * ``{"kind": …, "text": …, …}`` — rendered from those two fields.

    Returns the raw flash so a caller with extra payload (the fabric-import
    dict carries a column map) can render the rest, or ``None`` when there
    was nothing to show.
    """
    flash = st.session_state.pop(key, None)
    if not flash:
        return None
    if isinstance(flash, (tuple, list)) and len(flash) == 2:
        kind, message = flash
    elif isinstance(flash, dict):
        kind, message = flash.get("kind", "info"), flash.get("text", "")
    else:
        message = str(flash)
        kind = "error" if message.startswith("❌") else default_kind
    if kind not in _FLASH_KINDS:
        kind = "info"
    if message:
        getattr(st, kind)(message)
    return flash


# ---------------------------------------------------------------------------
# Destructive actions
# ---------------------------------------------------------------------------

DELETE_GLYPH = "🗑️"


def delete_button(label: str, key: str, *, confirm: str | None = None,
                  disabled: bool = False, width: str = "content",
                  help: str | None = None, container=None) -> bool:
    """A delete / remove button with the one glyph and style the app uses.

    Sixteen delete buttons used to choose between ``🗑`` and ``🗑️``, between
    plain and ``type="primary"``, and between a bare click and a tick-box.
    This is the one way to draw one.

    ``confirm`` — when given, a checkbox with that text gates the button: it
    stays disabled until ticked and turns primary (red) once it is, so the
    destructive click is deliberate.  Use it for anything that can't be
    undone (a user, a contract, a plan); leave it off for removing a row from
    a list the user is still editing.

    Returns True on the click (with the tick, when one is required).
    *container* lets the button live in a column; an empty *label* gives an
    icon-only button for tight rows.
    """
    host = container if container is not None else st
    armed = True
    if confirm:
        armed = bool(host.checkbox(confirm, key=f"{key}__confirm"))
    text = f"{DELETE_GLYPH} {label}".strip()
    clicked = host.button(
        text, key=key,
        type="primary" if (confirm and armed) else "secondary",
        disabled=disabled or not armed, width=width, help=help,
    )
    return bool(armed and not disabled and clicked)


# ---------------------------------------------------------------------------
# Output folder (save a copy beside the download)
# ---------------------------------------------------------------------------

def safe_filename(name: str, *, fallback: str = "output") -> str:
    """Strip characters Windows and Excel reject from a download filename."""
    cleaned = "".join(ch for ch in (name or "") if ch not in '\\/:*?"<>|').strip()
    return cleaned or fallback


def output_folder_input(key: str, kind: str, *, placeholder: str = r"D:\Exports") -> str:
    """Optional folder to drop a copy of a generated file into.

    The download button always works; this is for a shared drive other people
    read, so the file doesn't have to be downloaded and moved by hand.

    The last folder actually saved to under *kind* is remembered across
    sessions and comes back pre-filled; once more than one has been used a
    picker offers the recent ones.  *kind* is a logical bucket (see
    :func:`recent_folders`) — every field that writes to the same destination
    should share one.  Clearing the field sticks for the rest of the session;
    it is only seeded when the field has no value yet.
    """
    from ui.i18n import t as _t
    history = recent_folders(kind)
    if key not in st.session_state and history:
        st.session_state[key] = history[0]

    if len(history) > 1:
        pick_key = f"{key}__recent"

        def _apply_recent() -> None:
            chosen = st.session_state.get(pick_key)
            if chosen:
                st.session_state[key] = chosen

        st.selectbox(
            _t("Recent folders"), [""] + history, key=pick_key,
            on_change=_apply_recent, label_visibility="collapsed",
            format_func=lambda p: p or _t("Recent folders…"))

    return (st.text_input(
        _t("Also save a copy to this folder (optional)"), key=key,
        placeholder=placeholder,
        help=_t("Leave blank to just download. The folder must already exist "
                "and be writable from this machine. The last folder saved to "
                "is remembered and filled in next time.")) or "").strip()


def save_copy_to_folder(data: bytes, filename: str, folder: str, kind: str) -> None:
    """Write *data* to ``folder/filename`` and report the outcome inline.

    **Never replaces a file that is already there.** *folder* is usually a
    shared drive holding other people's work; a name collision took the
    existing file with no warning and no way back. A taken name gets ``_v2``,
    ``_v3`` … instead (the same rule the exporters use for their own output),
    and the message names the file that was actually written, so a version
    suffix is visible rather than silent.

    Best-effort and loud otherwise: a bad path tells the user which path
    failed and why, and never takes the download with it. The filename is
    reduced to its base name so a name carrying separators can't write
    outside *folder*.

    A folder is remembered under *kind* only once a file has actually landed
    in it, so the suggestions can't fill up with typos and dead paths.
    """
    if not folder:
        return
    from po_extractor.utils.file_utils import versioned_path
    from ui.i18n import t as _t
    safe = os.path.basename(str(filename)) or "output"
    stem, ext = os.path.splitext(safe)
    try:
        if not os.path.isdir(folder):
            st.warning(f"{_t('Folder not found — nothing saved:')} {folder}")
            return
        path = versioned_path(folder, stem, ext)
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        st.warning(f"{_t('Could not save to')} {folder} — {exc}")
        return
    remember_folder(kind, folder)
    st.success(f"{_t('Saved a copy to')} {path}")


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


def recent_folders(kind: str) -> list[str]:
    """Folders previously used for *kind*, most recently used first.

    *kind* is a logical bucket, not a widget key — every field that writes to
    the same destination should share one, so a folder entered in one place is
    offered everywhere it applies.
    """
    return _load_history(kind)


def remember_folder(kind: str, path: str) -> None:
    """Record *path* as the most recently used folder for *kind*.

    Call this only after a write actually succeeded: remembering a path the
    moment it is typed fills the history with half-finished paths and
    mistakes, and then offers them back as suggestions.
    """
    path = str(path or "").strip()
    if path:
        _push_history(kind, path)


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
        st.caption(_t(
            "Images are loaded from and saved here as `{style}_front.png` / `{style}_back.png` "
            "and also as `{picture_id}.png` for internal lookup. A style filed as a "
            "single `{style}.png` is used as its front photo. "
            "Leave blank to use the built-in default folder."
        ))

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
    _pid_file = f"{os.path.basename(str(picture_id))}.png"   # no path traversal
    for folder in (primary, EXTRACTED_IMAGES_DIR):
        path = os.path.join(folder, _pid_file)
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return f.read()
            except OSError:
                pass
    return None


def _canon_photo_name(name: str) -> str:
    """A .png filename reduced to what identifies it: lowercase, letters and
    digits only.

    The photo share is hand-maintained, and hand-typed names drift from the
    style number in ways exact matching can't see — ``TP3267-3_4 SLV.png``
    (space) for style ``TP3267-3_4SLV`` meant "no photo found", so the export
    silently fell back to the image embedded in the client's contract file,
    which put the WRONG garment on the 核料 doc. Dropping case, spaces and
    punctuation makes those spellings one key. Exact names are always tried
    first, so a canonical collision can only ever fill a gap, never override
    a properly named file.
    """
    import re as _re
    n = str(name).lower()
    if n.endswith(".png"):
        n = n[:-4]
    return _re.sub(r"[^a-z0-9]", "", n) + ".png"


def _photo_candidates(safe_style: str, pos: str) -> tuple[str, ...]:
    """Filenames accepted for a style's *pos* photo, best match first.

    A style with a single photo is filed under its bare name — most of the
    shared library is like that (286 of 427 files at last count had no
    ``_front`` sibling), and requiring the suffix reported every one of those
    styles as having no photo at all. A lone photo is the front one, which is
    also how the GIII side classifies it (``_photo_utils._classify_filename``
    calls an exact match "single" and uses it as the front).
    """
    if pos == "front":
        return (f"{safe_style}_front.png", f"{safe_style}.png")
    return (f"{safe_style}_back.png",)


def load_style_photo_pair(style: str, primary_dir: str | None = None) -> list:
    """Return ``[front_bytes|None, back_bytes|None]`` for *style*.

    Looks in the primary (configured) folder first, then the persistent
    :data:`EXTRACTED_IMAGES_DIR` fallback, for each name
    :func:`_photo_candidates` accepts.  Used by the buy-plan generator so
    photos still embed after a restart or a changed image folder.
    """
    import re as _re
    safe = _re.sub(r'[\\/:*?"<>|]', '_', str(style or ""))
    primary = primary_dir if primary_dir is not None else images_dir()
    # Lazy per-folder listing for the canonical fallback — one listdir per
    # folder at most, and only when an exact name missed.
    _canon_idx: dict[str, dict[str, str]] = {}

    def _canon_lookup(folder: str, cand: str) -> str | None:
        if folder not in _canon_idx:
            try:
                idx: dict[str, str] = {}
                for n in os.listdir(folder):
                    if n.lower().endswith(".png"):
                        idx.setdefault(_canon_photo_name(n), n)
                _canon_idx[folder] = idx
            except OSError:
                _canon_idx[folder] = {}
        return _canon_idx[folder].get(_canon_photo_name(cand))

    pair: list = []
    for pos in ("front", "back"):
        data = None
        # Folder outermost -- the configured library is fully searched before
        # the extracted-images fallback is touched. Same rule and reasoning as
        # load_style_photo_map above.
        for folder in (primary, EXTRACTED_IMAGES_DIR):
            for exact in (True, False):
                for cand in _photo_candidates(safe, pos):
                    fname = cand if exact else _canon_lookup(folder, cand)
                    if not fname:
                        continue
                    p = os.path.join(folder, fname)
                    if os.path.exists(p):
                        try:
                            with open(p, "rb") as fh:
                                data = fh.read()
                            break
                        except OSError:
                            pass
                if data is not None:
                    break
            if data is not None:
                break
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
    # Lowercased name → the name as it is actually spelled on disk. Windows and
    # the WebDAV mount are both case-insensitive, so a set membership test on
    # the raw names would miss a file that differs only in case. The second
    # dict is the canonical index (see _canon_photo_name): hand-typed names on
    # the share drift by spaces/punctuation, and an exact miss there used to
    # mean "no photo" — and a silent fall-through to the contract-embedded
    # image, i.e. possibly the wrong garment on the export.
    listings: list[tuple[str, dict[str, str], dict[str, str]]] = []
    for folder in (primary, EXTRACTED_IMAGES_DIR):
        try:
            names = os.listdir(folder)
            canon: dict[str, str] = {}
            for n in names:
                if n.lower().endswith(".png"):
                    canon.setdefault(_canon_photo_name(n), n)
            listings.append((folder, {n.lower(): n for n in names}, canon))
        except OSError:
            listings.append((folder, {}, {}))

    # Resolve which (folder, filename) each style/position should read from.
    wanted: list[tuple[str, int, str, str]] = []
    for style in styles:
        s = str(style or "").strip()
        if not s:
            continue
        safe = _re.sub(r'[\\/:*?"<>|]', '_', s)
        for idx, pos in enumerate(("front", "back")):
            # FOLDER is the outermost loop: the user's configured library is
            # searched to exhaustion -- every candidate name, exact spelling
            # then canonical -- before the extracted-images fallback is looked
            # at at all. The fallback holds images taken out of client
            # contracts, so it may only ever fill a gap, never outrank a real
            # photo. (It used to: candidate was the outer loop, so a stray
            # "{style}_front.png" in the fallback beat the curated
            # "{style}.png" in the library.)
            #
            # Within one folder the old order still holds: an explicit
            # `_front` beats a bare name, and an exact spelling beats a
            # canonical (space/punctuation-insensitive) one.
            hit = None
            for folder, names, canon in listings:
                for cand in _photo_candidates(safe, pos):
                    if cand.lower() in names:
                        hit = (folder, names[cand.lower()])
                        break
                if hit is None:
                    for cand in _photo_candidates(safe, pos):
                        ckey = _canon_photo_name(cand)
                        if ckey in canon:
                            hit = (folder, canon[ckey])
                            break
                if hit is not None:
                    break
            if hit:
                wanted.append((s, idx, hit[0], hit[1]))

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
    """Persist images extracted from a source file to *img_dir*.

    Saves two forms:
      {picture_id}.png          -- internal key used for DB lookups
      {style}_front.png / {style}_back.png -- human-readable front/back copies

    **Point this at EXTRACTED_IMAGES_DIR, never at the user's configured photo
    folder.** These bytes are whatever the client embedded in their contract,
    which can be a different garment; that folder is a hand-curated library,
    usually a shared drive. Writing there replaced real style photos under the
    same filename -- invisible until a 核料 doc showed the wrong garment (see
    tests/test_photo_never_overwritten.py). Reads fall back to
    EXTRACTED_IMAGES_DIR anyway when the library has no photo for a style, so
    nothing is lost by keeping our writes out of it.

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
                path = os.path.join(folder, f"{os.path.basename(str(pid))}.png")
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
                        # NEVER overwrite an existing photo -- same guard the
                        # {pid}.png write above already has.
                        #
                        # This folder is the user's own curated photo library
                        # (often a shared network drive). These bytes are only
                        # whatever the CLIENT embedded in their contract file,
                        # which can be a different garment entirely. Without
                        # this check every upload silently replaced the real
                        # style photo with the client's, and the wrong picture
                        # then went onto every 核料 doc and buy plan -- with
                        # nothing to show it had happened, because the
                        # filename never changed. (Found 2026-09-01:
                        # TP3267-3_4SLV_front.png on the share was byte-for-byte
                        # the contract's sleeveless top, stamped with that
                        # upload's timestamp.) A style with no photo yet still
                        # gets one; a curated photo is never touched again.
                        if not os.path.exists(fname):
                            with open(fname, "wb") as f:
                                f.write(img_bytes)
    except OSError as exc:
        from ui.i18n import t as _t
        st.warning(_t(
            "⚠️ Could not save images to '{folder}' ({exc}). Photos will still be "
            "found via the local extracted-images fallback; check the configured "
            "image folder in Admin Settings if this persists."
        ).format(folder=folder, exc=exc))


# Ceiling on how many bytes of full-resolution photos one call may hold in
# memory at once.  Source photos run to ~15 MB each here, so an unbounded load
# of a few hundred styles is hundreds of MB — enough to raise MemoryError on a
# busy machine and take the whole tab down with it.  Loading stops at the
# ceiling and the skipped IDs are reported rather than silently dropped.
_IMAGE_CACHE_BUDGET_BYTES = 192 * 1024 * 1024

# Longest edge of a table thumbnail, in pixels.  Table cells render these a
# few dozen pixels wide; anything larger is bytes nobody sees.
_THUMB_MAX_PX = 160

# Picture IDs the most recent load skipped, and why.
_last_image_skips: list[str] = []


def get_last_image_skips() -> list[str]:
    """Picture IDs the last image load skipped (budget or read failure)."""
    return list(_last_image_skips)


def _photo_path(pid, img_dir: str | None = None) -> str | None:
    """Resolve a picture ID to a file, configured folder first."""
    primary = img_dir if img_dir is not None else images_dir()
    for folder in (primary, EXTRACTED_IMAGES_DIR):
        path = os.path.join(folder, f"{os.path.basename(str(pid))}.png")
        if os.path.exists(path):
            return path
    return None


def build_image_cache_for_ids(picture_ids,
                              session_cache_key: str = "se_image_cache",
                              img_dir: str | None = None,
                              budget_bytes: int = _IMAGE_CACHE_BUDGET_BYTES) -> dict:
    """Return {picture_id: bytes} for the given IDs, loading from session then disk.

    Full-resolution bytes — this feeds Excel embedding, so images are never
    downscaled here.  For a table thumbnail use
    :func:`build_thumbnail_data_urls` instead; inlining these as base64 costs
    a third again on top of already-large files.

    Already-loaded images are served from the session-state cache so repeated
    Generate presses skip all disk I/O for images that were loaded previously.
    Newly loaded images are written back into the session cache so future calls
    (within the same session) are instant.

    Loading stops once *budget_bytes* of newly-read data is reached; a read
    that fails — including MemoryError, which a bare ``except OSError`` used
    to let escape and kill the calling tab — skips that image only.  Skipped
    IDs are available from :func:`get_last_image_skips`.

    The session cache as a whole is held under the same ceiling: the per-call
    budget alone let every new PO set add its own budget's worth of photos,
    so a session that generated buy plans for several different sets could
    still climb to the MemoryError the ceiling exists to prevent.  Entries
    not needed by the current call are evicted oldest-first once the total
    passes the budget.
    """
    global _last_image_skips
    _last_image_skips = []
    session_cache: dict = st.session_state.setdefault(session_cache_key, {})
    result: dict = {}
    spent = 0
    for pid in picture_ids:
        pid = str(pid).strip() if pid else ""
        if not pid:
            continue
        if pid in session_cache:
            # Already in session — free hit, and not charged to the budget.
            result[pid] = session_cache[pid]
            continue
        path = _photo_path(pid, img_dir)
        if path is None:
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if spent + size > budget_bytes and result:
            _last_image_skips.append(f"{pid} (memory budget reached)")
            continue
        try:
            with open(path, "rb") as _f:
                b = _f.read()
        except (OSError, MemoryError) as exc:
            _last_image_skips.append(f"{pid} ({type(exc).__name__})")
            continue
        spent += len(b)
        session_cache[pid] = b
        result[pid] = b

    # Cap the WHOLE cache, not just this call's reads. Oldest entries first
    # (dict insertion order); everything this call returned is kept.
    total = sum(len(b) for b in session_cache.values())
    if total > budget_bytes:
        for old_pid in list(session_cache):
            if total <= budget_bytes:
                break
            if old_pid in result:
                continue
            total -= len(session_cache[old_pid])
            del session_cache[old_pid]
    return result


def build_thumbnail_data_urls(picture_ids,
                              session_cache_key: str = "photo_thumb_cache",
                              img_dir: str | None = None,
                              max_px: int = _THUMB_MAX_PX) -> dict:
    """Return {picture_id: data-URL} of small thumbnails for table columns.

    Downscaling before base64 is the whole point.  A source photo here can be
    15 MB; inlined as a data URL that becomes ~20 MB of string, and a page of
    them is hundreds of MB held in the server *and* shipped to the browser —
    for cells rendered a few dozen pixels wide.  A ``max_px`` thumbnail is a
    few tens of KB.

    Thumbnails are cached in their own session key so the full-resolution
    originals aren't retained alongside them.  An image that can't be read or
    decoded is skipped, never raised — a broken photo must not take down the
    table it appears in.
    """
    session_cache: dict = st.session_state.setdefault(session_cache_key, {})
    result: dict = {}
    for pid in picture_ids:
        pid = str(pid).strip() if pid else ""
        if not pid:
            continue
        if pid in session_cache:
            result[pid] = session_cache[pid]
            continue
        path = _photo_path(pid, img_dir)
        if path is None:
            continue
        url = _thumbnail_data_url(path, max_px)
        if url:
            session_cache[pid] = url
            result[pid] = url
        else:
            _last_image_skips.append(pid)
    return result


def _thumbnail_data_url(path: str, max_px: int) -> str | None:
    """Downscale *path* to a base64 PNG data URL, or None if it can't be read."""
    try:
        from PIL import Image
    except ImportError:
        # No PIL — fall back to the original bytes, but only for files small
        # enough that inlining them is harmless.
        try:
            if os.path.getsize(path) > 256 * 1024:
                return None
            with open(path, "rb") as fh:
                return ("data:image/png;base64,"
                        + base64.b64encode(fh.read()).decode())
        except (OSError, MemoryError):
            return None

    buf = io.BytesIO()
    try:
        with Image.open(path) as im:
            im.draft("RGB", (max_px, max_px))   # cheap pre-scale where supported
            im = im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB")
            im.thumbnail((max_px, max_px))
            im.save(buf, format="PNG", optimize=True)
    except (OSError, MemoryError, ValueError) as exc:
        _last_image_skips.append(f"{os.path.basename(path)} ({type(exc).__name__})")
        return None
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
