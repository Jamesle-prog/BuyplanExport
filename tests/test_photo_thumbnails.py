"""Tests for table-photo loading.

Source photos in this app run to ~15 MB each.  Inlining them into a table as
base64 data URLs cost a third again on top of that — hundreds of megabytes
held server-side and shipped to the browser for cells rendered a few dozen
pixels wide — and raised MemoryError on a loaded machine, which a bare
``except OSError`` let escape and kill the whole tab.
"""
from __future__ import annotations

import base64
import io
import os

import pytest
from PIL import Image

from ui.shared import (
    _THUMB_MAX_PX, _thumbnail_data_url, build_image_cache_for_ids,
    get_last_image_skips,
)


def _png(path: str, size: tuple[int, int] = (1200, 1600)) -> str:
    """Write a PNG of noise, so it can't compress away to nothing.

    Built straight from a bytes buffer: putdata() with a list of per-pixel
    tuples allocates millions of Python objects and raised MemoryError here
    while testing a memory fix.
    """
    im = Image.frombytes("RGB", size, os.urandom(size[0] * size[1] * 3))
    im.save(path, format="PNG")
    return path


def _decode(url: str) -> bytes:
    assert url.startswith("data:image/png;base64,")
    return base64.b64decode(url.split(",", 1)[1])


# ── Thumbnailing ────────────────────────────────────────────────────────────

def test_thumbnail_is_orders_of_magnitude_smaller_than_the_source(tmp_path):
    src = _png(str(tmp_path / "big.png"))
    source_inlined = os.path.getsize(src) * 4 / 3      # base64 of the original
    url = _thumbnail_data_url(src, _THUMB_MAX_PX)
    assert url and len(url) < source_inlined / 20


def test_thumbnail_fits_the_pixel_cap_and_keeps_aspect_ratio(tmp_path):
    url = _thumbnail_data_url(_png(str(tmp_path / "tall.png"), (600, 1200)),
                              _THUMB_MAX_PX)
    with Image.open(io.BytesIO(_decode(url))) as im:
        assert max(im.size) <= _THUMB_MAX_PX
        assert im.width * 2 == im.height          # 600x1200 stays 1:2


def test_small_image_is_not_scaled_up(tmp_path):
    url = _thumbnail_data_url(_png(str(tmp_path / "small.png"), (40, 60)),
                              _THUMB_MAX_PX)
    with Image.open(io.BytesIO(_decode(url))) as im:
        assert im.size == (40, 60)


def test_transparency_is_preserved(tmp_path):
    path = str(tmp_path / "alpha.png")
    Image.new("RGBA", (300, 300), (255, 0, 0, 0)).save(path)
    with Image.open(io.BytesIO(_decode(_thumbnail_data_url(path, 64)))) as im:
        assert im.mode == "RGBA"


def test_a_corrupt_image_is_skipped_not_raised(tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"this is not a PNG")
    assert _thumbnail_data_url(str(bad), _THUMB_MAX_PX) is None


def test_a_missing_file_is_skipped_not_raised(tmp_path):
    assert _thumbnail_data_url(str(tmp_path / "nope.png"), _THUMB_MAX_PX) is None


# ── Full-resolution loader ──────────────────────────────────────────────────

class _FakeSessionState(dict):
    """Minimal stand-in for st.session_state (attribute + item access)."""

    def __getattr__(self, k):
        return self[k]

    def __setattr__(self, k, v):
        self[k] = v


@pytest.fixture
def session(monkeypatch):
    import ui.shared as shared

    state = _FakeSessionState()
    monkeypatch.setattr(shared.st, "session_state", state)
    return state


def test_full_res_loader_returns_original_bytes(tmp_path, session, monkeypatch):
    """Excel embedding depends on this path — it must NOT downscale."""
    import ui.shared as shared

    src = _png(str(tmp_path / "PID1.png"), (300, 300))
    monkeypatch.setattr(shared, "images_dir", lambda: str(tmp_path))
    loaded = build_image_cache_for_ids(["PID1"], img_dir=str(tmp_path))
    assert loaded["PID1"] == open(src, "rb").read()


def test_budget_stops_loading_and_reports_what_it_skipped(tmp_path, session,
                                                          monkeypatch):
    import ui.shared as shared

    monkeypatch.setattr(shared, "images_dir", lambda: str(tmp_path))
    for i in range(4):
        _png(str(tmp_path / f"P{i}.png"), (500, 500))

    one = os.path.getsize(str(tmp_path / "P0.png"))
    loaded = build_image_cache_for_ids(
        [f"P{i}" for i in range(4)], img_dir=str(tmp_path),
        budget_bytes=int(one * 1.5))

    assert 0 < len(loaded) < 4                 # some in, some skipped
    assert get_last_image_skips()              # and the skips are reported
    assert all("budget" in s for s in get_last_image_skips())


def test_budget_never_returns_nothing(tmp_path, session, monkeypatch):
    """A single image larger than the whole budget is still loaded — an empty
    table is worse than briefly exceeding the ceiling."""
    import ui.shared as shared

    monkeypatch.setattr(shared, "images_dir", lambda: str(tmp_path))
    _png(str(tmp_path / "HUGE.png"), (800, 800))
    loaded = build_image_cache_for_ids(["HUGE"], img_dir=str(tmp_path),
                                       budget_bytes=1)
    assert "HUGE" in loaded


def test_unreadable_image_does_not_kill_the_caller(tmp_path, session,
                                                    monkeypatch):
    """MemoryError used to escape ``except OSError`` and take down the tab."""
    import builtins

    import ui.shared as shared

    monkeypatch.setattr(shared, "images_dir", lambda: str(tmp_path))
    _png(str(tmp_path / "OK.png"), (100, 100))
    _png(str(tmp_path / "BOOM.png"), (100, 100))

    real_open = builtins.open

    def exploding_open(path, *a, **kw):
        if "BOOM" in str(path):
            raise MemoryError("simulated")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", exploding_open)
    loaded = build_image_cache_for_ids(["BOOM", "OK"], img_dir=str(tmp_path))

    assert "OK" in loaded and "BOOM" not in loaded
    assert any("BOOM" in s for s in get_last_image_skips())


def test_session_cache_serves_repeat_calls(tmp_path, session, monkeypatch):
    import ui.shared as shared

    monkeypatch.setattr(shared, "images_dir", lambda: str(tmp_path))
    _png(str(tmp_path / "PID1.png"), (100, 100))
    build_image_cache_for_ids(["PID1"], img_dir=str(tmp_path))

    os.remove(str(tmp_path / "PID1.png"))          # gone from disk
    again = build_image_cache_for_ids(["PID1"], img_dir=str(tmp_path))
    assert "PID1" in again                          # still served from session
