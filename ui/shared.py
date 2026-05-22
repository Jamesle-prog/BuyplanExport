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
                st.rerun()
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
    folder = img_dir if img_dir is not None else images_dir()
    path = os.path.join(folder, f"{picture_id}.png")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None


def save_images_to_disk(image_dict: dict,
                        style_pid_map: dict[str, list[str]] | None = None,
                        img_dir: str | None = None) -> None:
    """Persist images to the configured folder.

    Saves two forms:
      {picture_id}.png          -- internal key used for DB lookups
      {style}_front.png / {style}_back.png -- human-readable front/back copies
    """
    import re as _re
    folder = img_dir if img_dir is not None else images_dir()
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


def build_image_cache_for_ids(picture_ids,
                              session_cache_key: str = "se_image_cache",
                              img_dir: str | None = None) -> dict:
    """Return {picture_id: bytes} for the given IDs, loading from session then disk."""
    result = {}
    for pid in picture_ids:
        pid = str(pid).strip() if pid else ""
        if pid:
            b = load_image(pid, session_cache_key=session_cache_key, img_dir=img_dir)
            if b:
                result[pid] = b
    return result
