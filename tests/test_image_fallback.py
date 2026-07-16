"""Tests for the persistent extracted-images fallback.

Images extracted from source spreadsheets are saved to a dedicated
``EXTRACTED_IMAGES_DIR`` in addition to the user's configured image folder, so
a later buy-plan run can still find them after a restart clears the in-memory
cache or when the configured folder was changed/emptied.  These tests cover the
two-folder ``load_style_photo_pair`` resolution.
"""
from __future__ import annotations

import io

from PIL import Image

import ui.shared as shared


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_load_style_photo_pair_falls_back_to_extracted(tmp_path, monkeypatch):
    primary = tmp_path / "primary"; primary.mkdir()
    extracted = tmp_path / "extracted"; extracted.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))

    # Present only in the extracted fallback, nothing in the primary folder.
    (extracted / "DR1_front.png").write_bytes(_png())

    pair = shared.load_style_photo_pair("DR1", str(primary))
    assert pair[0] is not None          # found via the extracted fallback
    assert pair[1] is None              # no back image anywhere


def test_load_style_photo_pair_primary_takes_precedence(tmp_path, monkeypatch):
    primary = tmp_path / "primary"; primary.mkdir()
    extracted = tmp_path / "extracted"; extracted.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))

    (primary / "DR1_front.png").write_bytes(b"PRIMARY")
    (extracted / "DR1_front.png").write_bytes(b"EXTRACTED")

    pair = shared.load_style_photo_pair("DR1", str(primary))
    assert pair[0] == b"PRIMARY"        # configured folder wins over fallback


def test_load_style_photo_pair_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(tmp_path / "nope"))
    assert shared.load_style_photo_pair("DRX", str(tmp_path)) == [None, None]


def test_load_style_photo_pair_sanitizes_style_name(tmp_path, monkeypatch):
    # A style with filesystem-illegal chars is sanitised the same way it was
    # saved (save_images_to_disk uses the same regex).
    extracted = tmp_path / "extracted"; extracted.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))
    (extracted / "DR_5_A_front.png").write_bytes(_png())

    pair = shared.load_style_photo_pair("DR/5:A", str(tmp_path / "primary_missing"))
    assert pair[0] is not None


def test_save_images_to_disk_unreachable_folder_does_not_raise(tmp_path, monkeypatch):
    """A misconfigured/unreachable image folder (e.g. a network path this
    install can't authenticate to -- WinError 1326) must warn, not crash the
    whole upload flow. The real PO/contract data is already saved to the DB
    by the time this runs; photo embedding is best-effort on top of that."""
    def _raise(*_a, **_kw):
        raise OSError(1326, "Logon failure: unknown user name or bad password")
    monkeypatch.setattr(shared.os, "makedirs", _raise)

    # Must not raise.
    shared.save_images_to_disk({"ID_1": _png()}, img_dir=str(tmp_path / "unreachable"))


def test_save_images_to_disk_still_writes_to_a_valid_folder(tmp_path):
    folder = tmp_path / "images"
    shared.save_images_to_disk(
        {"ID_1": _png()},
        style_pid_map={"DR1": ["ID_1"]},
        img_dir=str(folder),
    )
    assert (folder / "ID_1.png").exists()
    assert (folder / "DR1_front.png").exists()
