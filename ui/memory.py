"""Lightweight memory management — keep RAM and the on-disk image cache bounded.

Two unbounded growth points motivate this:

  1. **Disk** — the persistent ``data/extracted_images`` folder (added in
     v2.23.0) gains files on every processing run and is never cleaned.
     :func:`prune_extracted_images` caps it by file count and total size,
     deleting the oldest first.  Called automatically after processing.

  2. **RAM** — the app parks large blobs in ``st.session_state`` (generated
     buy-plan / 核料 / download bytes, and the style-photo cache) that only
     clear on sign-out.  :func:`trim_image_cache` bounds the photo cache
     automatically (safe: lookups fall back to disk), and
     :func:`free_session_memory` (a manual sidebar button) drops all of them
     on demand plus clears module-level caches.

Every function here is best-effort and never raises into the caller.
"""
from __future__ import annotations

import os

import streamlit as st

from ui.session_keys import SK

# ── On-disk: extracted-images folder caps ────────────────────────────────────
EXTRACTED_IMAGES_MAX_FILES = 4000
EXTRACTED_IMAGES_MAX_MB    = 300

# ── In-RAM: style-photo cache cap (safe — misses re-load from disk) ───────────
IMAGE_CACHE_MAX_ITEMS = 1000

# Large transient blobs that are safe to drop between tasks. Clearing the file
# blobs just removes their download buttons until regenerated; clearing the
# image cache is safe because lookups fall back to the extracted-images folder.
_HEAVY_KEYS = (
    SK.SE_IMAGE_CACHE, SK.SE_BP_BYTES, SK.SE_NK_BYTES,
    SK.SE_DL_BYTES, SK.SE_WL_BYTES, SK.SE_MASKED_ZIP,
    SK.HISTORY_BP_BYTES,
)


def prune_extracted_images(folder: str | None = None, *,
                           max_files: int = EXTRACTED_IMAGES_MAX_FILES,
                           max_mb: int = EXTRACTED_IMAGES_MAX_MB) -> int:
    """Delete the oldest files in *folder* until it is within BOTH the file-count
    and total-size caps.  Returns the number of files removed.  Never raises.
    """
    if folder is None:
        from ui.shared import EXTRACTED_IMAGES_DIR
        folder = EXTRACTED_IMAGES_DIR
    try:
        names = os.listdir(folder)
    except OSError:
        return 0

    files: list[tuple[str, float, int]] = []
    total = 0
    _base = os.path.realpath(folder)
    for name in names:
        p = os.path.join(folder, name)
        try:
            if not os.path.isfile(p):
                continue
            # Only ever delete inside the images folder — a symlink whose
            # real target escapes the folder is skipped, so os.remove below
            # can never touch an arbitrary file.
            if os.path.commonpath([_base, os.path.realpath(p)]) != _base:
                continue
            stt = os.stat(p)
        except (OSError, ValueError):
            continue
        files.append((p, stt.st_mtime, stt.st_size))
        total += stt.st_size

    files.sort(key=lambda e: e[1])          # oldest first
    max_bytes = max_mb * 1024 * 1024
    remaining = len(files)
    removed = 0
    for p, _mtime, sz in files:
        if remaining <= max_files and total <= max_bytes:
            break
        try:
            os.remove(p)
            total -= sz
            remaining -= 1
            removed += 1
        except OSError:
            pass
    return removed


def trim_image_cache(cache: dict | None = None,
                     max_items: int = IMAGE_CACHE_MAX_ITEMS) -> int:
    """Evict the oldest entries from the in-memory style-photo cache beyond
    *max_items*.  Safe because image lookups fall back to the persistent
    extracted-images folder on a cache miss.  Returns the number evicted.

    Pass *cache* explicitly (a dict) to trim it directly; otherwise the session
    cache (``SK.SE_IMAGE_CACHE``) is used.
    """
    own = cache is None
    if own:
        cache = st.session_state.get(SK.SE_IMAGE_CACHE)
    if not isinstance(cache, dict) or len(cache) <= max_items:
        return 0
    excess = len(cache) - max_items
    for k in list(cache.keys())[:excess]:   # dict preserves insertion order
        cache.pop(k, None)
    return excess


def _blob_size(v) -> int:
    """Approximate the in-RAM byte size of a session blob (bytes / nested
    dict / list of bytes).  Non-blob values count as 0."""
    if v is None:
        return 0
    if isinstance(v, (bytes, bytearray)):
        return len(v)
    if isinstance(v, dict):
        return sum(_blob_size(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return sum(_blob_size(x) for x in v)
    return 0


def estimate_session_blob_bytes() -> int:
    """Approximate total bytes held by the heavy session blobs."""
    return sum(_blob_size(st.session_state.get(k)) for k in _HEAVY_KEYS)


def free_session_memory() -> int:
    """Drop the heavy transient blobs from session_state and clear module-level
    caches.  Returns the approximate bytes freed.  Download buttons for already
    generated files disappear until regenerated; style photos reload from disk.
    """
    freed = estimate_session_blob_bytes()
    for k in _HEAVY_KEYS:
        if k in st.session_state:
            st.session_state[k] = {} if isinstance(st.session_state[k], dict) else None
    # Module-level AI colour caches (process-lifetime otherwise).
    try:
        from po_extractor.lookups import color_ai_enhance as _cae
        _cae._cache.clear()
        _cae._match_cache.clear()
    except Exception:
        pass
    return freed


def render_sidebar_memory() -> None:
    """Sidebar control: show the approximate held-blob size + a free button."""
    from ui.i18n import t
    approx_mb = estimate_session_blob_bytes() / (1024 * 1024)
    with st.expander(f"🧹 {t('Memory')} (~{approx_mb:.0f} MB)"):
        st.caption(t(
            "Frees cached downloads and style-photo memory held for this session. "
            "Generated files must be re-created afterwards; style photos reload "
            "from disk automatically."
        ))
        if st.button(t("Free memory now"), key="mem_free_btn",
                     use_container_width=True):
            freed_mb = free_session_memory() / (1024 * 1024)
            st.success(f"{t('Freed')} ~{freed_mb:.0f} MB.")
            st.rerun()
