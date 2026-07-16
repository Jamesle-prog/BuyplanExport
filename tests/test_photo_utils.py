"""Tests for the Photo1/Photo2 disk-path sandbox in resolve_photo_pair.

Security fix: the legacy fallback treated a Photo1/Photo2 cell value (read
straight from a user-uploaded PO/Excel file — fully attacker-controlled) as
a literal server-side file path with no restriction, so any file the server
process could read would get embedded into the output .xlsx. Any absolute
path or ``../`` traversal attempt must now be rejected unless it resolves
inside the configured (or default) images folder.
"""
from __future__ import annotations

import pandas as pd

from po_extractor.exporters._photo_utils import (
    _DEFAULT_IMAGES_DIR, _is_within_images_dir, resolve_photo_pair,
)


# ── containment helper ────────────────────────────────────────────────────────

def test_is_within_images_dir_accepts_path_inside(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    f = images_dir / "photo.png"
    f.write_bytes(b"x")
    assert _is_within_images_dir(str(f), str(images_dir))


def test_is_within_images_dir_rejects_path_outside(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"x")
    assert not _is_within_images_dir(str(outside), str(images_dir))


def test_is_within_images_dir_rejects_traversal(tmp_path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_bytes(b"x")
    traversal = str(images_dir / ".." / "secret.txt")
    assert not _is_within_images_dir(traversal, str(images_dir))


def test_is_within_images_dir_rejects_sibling_dir_with_similar_prefix(tmp_path):
    """A naive startswith(base) check would wrongly accept 'images_evil' as
    being inside 'images' — commonpath must reject it."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    sibling = tmp_path / "images_evil"
    sibling.mkdir()
    leak = sibling / "leak.txt"
    leak.write_bytes(b"x")
    assert not _is_within_images_dir(str(leak), str(images_dir))


def test_is_within_images_dir_defaults_to_shared_default_when_not_given():
    assert _is_within_images_dir(_DEFAULT_IMAGES_DIR + "/x.png", None)
    assert not _is_within_images_dir("C:/Windows/win.ini", None)


# ── resolve_photo_pair: legacy Photo1/Photo2 path fallback ───────────────────

def test_resolve_photo_pair_rejects_path_outside_images_dir(tmp_path):
    """A path outside the configured images folder must be rejected even
    though the file genuinely exists and is readable — this is exactly the
    arbitrary-file-read scenario the fix closes."""
    secret = tmp_path / "secret.bin"
    secret.write_bytes(b"SECRET-SERVER-DATA")
    images_dir = tmp_path / "images"
    images_dir.mkdir()

    row = pd.Series({"Photo1": str(secret), "Photo2": None})
    front, back = resolve_photo_pair("NOMATCH_STYLE", row, {}, images_dir=str(images_dir))
    assert front is None and back is None


def test_resolve_photo_pair_allows_path_inside_configured_images_dir(tmp_path):
    """Normal case: Photo1 points at a real file INSIDE the configured
    images folder — must still resolve (no regression for legitimate use)."""
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    photo = images_dir / "some_photo.png"
    photo.write_bytes(b"REAL-PHOTO-BYTES")

    row = pd.Series({"Photo1": str(photo), "Photo2": None})
    front, back = resolve_photo_pair("NOMATCH_STYLE", row, {}, images_dir=str(images_dir))
    assert front == str(photo)
    assert back is None


def test_resolve_photo_pair_rejects_traversal_via_photo_column(tmp_path):
    secret = tmp_path / "secret.bin"
    secret.write_bytes(b"SECRET")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    traversal = str(images_dir / ".." / "secret.bin")

    row = pd.Series({"Photo1": traversal, "Photo2": None})
    front, _back = resolve_photo_pair("NOMATCH_STYLE", row, {}, images_dir=str(images_dir))
    assert front is None


def test_resolve_photo_pair_photo_map_matches_unaffected_by_sandbox():
    """Strategies 1/2 (style-keyed / filename-pattern in photo_map) never
    touch the filesystem — they must keep working regardless of images_dir,
    confirming the sandbox doesn't weaken the primary lookup paths."""
    photo_map = {"BL3404_front.png": b"BYTES"}
    front, _back = resolve_photo_pair("BL3404", pd.Series(dtype=object), photo_map,
                                      images_dir="/completely/unrelated/path")
    assert front == b"BYTES"
