"""Tests for ui/memory.py — the bounded on-disk prune, image-cache trim, and
session blob-size estimation.

Session-dependent functions (estimate_session_blob_bytes / free_session_memory
/ render_sidebar_memory) need a Streamlit runtime, so here we cover the pure
pieces: prune_extracted_images (disk), trim_image_cache (explicit dict), and
_blob_size.
"""
from __future__ import annotations

import os
import time

from ui import memory


def _write(path, size):
    with open(path, "wb") as f:
        f.write(b"x" * size)


def test_prune_extracted_images_respects_file_count_cap(tmp_path):
    folder = tmp_path / "ex"; folder.mkdir()
    for i in range(10):
        p = folder / f"img{i}.png"
        _write(p, 10)
        # stagger mtimes so "oldest" is well-defined
        os.utime(p, (1000 + i, 1000 + i))

    removed = memory.prune_extracted_images(str(folder), max_files=4, max_mb=9999)
    assert removed == 6
    remaining = sorted(os.listdir(folder))
    assert remaining == ["img6.png", "img7.png", "img8.png", "img9.png"]  # newest kept


def test_prune_extracted_images_respects_size_cap(tmp_path):
    folder = tmp_path / "ex"; folder.mkdir()
    # 5 files × 1 MB each; cap at 2 MB → 3 oldest removed
    for i in range(5):
        p = folder / f"img{i}.png"
        _write(p, 1024 * 1024)
        os.utime(p, (2000 + i, 2000 + i))

    removed = memory.prune_extracted_images(str(folder), max_files=9999, max_mb=2)
    assert removed == 3
    assert sorted(os.listdir(folder)) == ["img3.png", "img4.png"]


def test_prune_extracted_images_missing_folder_is_noop(tmp_path):
    assert memory.prune_extracted_images(str(tmp_path / "nope")) == 0


def test_prune_extracted_images_within_caps_removes_nothing(tmp_path):
    folder = tmp_path / "ex"; folder.mkdir()
    _write(folder / "a.png", 10)
    _write(folder / "b.png", 10)
    assert memory.prune_extracted_images(str(folder), max_files=10, max_mb=10) == 0
    assert len(os.listdir(folder)) == 2


def test_trim_image_cache_evicts_oldest_beyond_cap():
    cache = {f"pid{i}": b"x" for i in range(1005)}
    evicted = memory.trim_image_cache(cache, max_items=1000)
    assert evicted == 5
    assert len(cache) == 1000
    assert "pid0" not in cache          # oldest inserted evicted
    assert "pid1004" in cache           # newest kept


def test_trim_image_cache_under_cap_is_noop():
    cache = {"a": b"1", "b": b"2"}
    assert memory.trim_image_cache(cache, max_items=10) == 0
    assert len(cache) == 2


def test_blob_size_handles_bytes_dicts_and_lists():
    assert memory._blob_size(b"x" * 100) == 100
    assert memory._blob_size({"a": b"xx", "b": b"yyy"}) == 5
    assert memory._blob_size([b"a", b"bb", None]) == 3
    assert memory._blob_size(None) == 0
    assert memory._blob_size("not a blob") == 0
