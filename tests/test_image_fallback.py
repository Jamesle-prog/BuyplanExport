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


# ---------------------------------------------------------------------------
# load_style_photo_map — batch loader (one listing per folder, no per-style
# probes; critical on network/Mountain Duck image folders)
# ---------------------------------------------------------------------------

def test_photo_map_batch_loads_from_primary_and_fallback(tmp_path, monkeypatch):
    primary = tmp_path / "primary"; primary.mkdir()
    extracted = tmp_path / "extracted"; extracted.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))

    (primary / "DR1_front.png").write_bytes(_png())
    (primary / "DR1_back.png").write_bytes(_png())
    (extracted / "DR2_front.png").write_bytes(_png())   # only in fallback

    out = shared.load_style_photo_map(["DR1", "DR2", "DR3"], str(primary))
    assert set(out) == {"DR1", "DR2"}                    # DR3 photo-less -> omitted
    assert out["DR1"][0] is not None and out["DR1"][1] is not None
    assert out["DR2"][0] is not None and out["DR2"][1] is None


def test_photo_map_unlistable_primary_degrades_fast_not_per_file(tmp_path, monkeypatch):
    """An unreachable primary folder must cost exactly ONE failed directory
    enumeration -- never a per-style probe -- and the extracted fallback must
    still work."""
    extracted = tmp_path / "extracted"; extracted.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))
    (extracted / "DR9_front.png").write_bytes(_png())

    listdir_calls = []
    real_listdir = shared.os.listdir

    def _listdir(folder):
        listdir_calls.append(str(folder))
        if "unreachable" in str(folder):
            raise OSError(1326, "Logon failure")
        return real_listdir(folder)
    monkeypatch.setattr(shared.os, "listdir", _listdir)

    out = shared.load_style_photo_map(
        [f"DR{i}" for i in range(50)], str(tmp_path / "unreachable"),
    )
    assert set(out) == {"DR9"}
    # One enumeration per PHOTO folder regardless of 50 styles (the local
    # photo_cache dir listing is separate bookkeeping, not a folder probe).
    photo_folder_lists = [c for c in listdir_calls
                          if "unreachable" in c or "extracted" in c]
    assert len(photo_folder_lists) == 2


def test_photo_map_caches_external_folder_reads(tmp_path, monkeypatch):
    """Bytes from an EXTERNAL (e.g. network-mounted) folder are mirrored
    locally, so a second run never re-reads the source -- the fix for a
    Mountain Duck image folder costing ~20 MB of transfer per generation."""
    external = tmp_path / "mount"; external.mkdir()
    extracted = tmp_path / "extracted"; extracted.mkdir()
    cache = tmp_path / "photo_cache"
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))
    monkeypatch.setattr(shared, "PHOTO_CACHE_DIR", str(cache))
    src = external / "DR1_front.png"
    src.write_bytes(_png())

    opened = []
    import builtins
    real_builtin_open = builtins.open

    def _tracking_open(path, *a, **kw):
        if str(external) in str(path):
            opened.append(str(path))
        return real_builtin_open(path, *a, **kw)
    monkeypatch.setattr(builtins, "open", _tracking_open)

    first = shared.load_style_photo_map(["DR1"], str(external))
    assert first["DR1"][0] is not None
    assert len(opened) == 1                      # source read once

    second = shared.load_style_photo_map(["DR1"], str(external))
    assert second["DR1"][0] == first["DR1"][0]
    assert len(opened) == 1                      # served from local cache


def test_photo_map_cache_invalidates_on_source_change(tmp_path, monkeypatch):
    """A changed source file yields a different cache key (size+mtime), so
    the new bytes are picked up -- the cache can never serve stale photos."""
    external = tmp_path / "mount"; external.mkdir()
    extracted = tmp_path / "extracted"; extracted.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))
    monkeypatch.setattr(shared, "PHOTO_CACHE_DIR", str(tmp_path / "photo_cache"))
    src = external / "DR1_front.png"
    src.write_bytes(_png())
    first = shared.load_style_photo_map(["DR1"], str(external))["DR1"][0]

    bigger = _png() + b"\x00" * 64               # different size -> different key
    src.write_bytes(bigger)
    second = shared.load_style_photo_map(["DR1"], str(external))["DR1"][0]
    assert second == bigger and second != first


def test_photo_map_sanitizes_style_names_like_pair_loader(tmp_path, monkeypatch):
    extracted = tmp_path / "extracted"; extracted.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))
    (extracted / "DR_5_A_front.png").write_bytes(_png())

    out = shared.load_style_photo_map(["DR/5:A"], str(tmp_path / "missing"))
    assert out["DR/5:A"][0] is not None


# ── Styles filed as a single photo (no _front suffix) ───────────────────────
#
# Most of the shared style library is like this: 286 of the 427 files on the
# Zalando share had no ``_front`` sibling, and requiring the suffix reported
# every one of those styles as having no photo at all while the file sat right
# there in the folder.

def test_bare_style_png_is_used_as_the_front_photo(tmp_path, monkeypatch):
    primary = tmp_path / "primary"; primary.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(tmp_path / "none"))
    (primary / "DR5108.png").write_bytes(_png())

    assert shared.load_style_photo_pair("DR5108", str(primary))[0] is not None
    assert shared.load_style_photo_map(["DR5108"], str(primary))["DR5108"][0] \
        is not None


def test_bare_style_png_is_never_taken_as_the_back_photo(tmp_path, monkeypatch):
    primary = tmp_path / "primary"; primary.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(tmp_path / "none"))
    (primary / "DR5108.png").write_bytes(_png())

    assert shared.load_style_photo_pair("DR5108", str(primary))[1] is None
    assert shared.load_style_photo_map(["DR5108"], str(primary))["DR5108"][1] \
        is None


def test_explicit_front_wins_over_the_bare_name(tmp_path, monkeypatch):
    """A style with both filings must use the one that says which side it is —
    including when the explicit one is only in the extracted fallback."""
    primary = tmp_path / "primary"; primary.mkdir()
    extracted = tmp_path / "extracted"; extracted.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(extracted))
    front = _png()
    (extracted / "DR5110_front.png").write_bytes(front)
    (primary / "DR5110.png").write_bytes(b"not a png")     # bare, primary

    assert shared.load_style_photo_pair("DR5110", str(primary))[0] == front
    assert shared.load_style_photo_map(["DR5110"], str(primary))["DR5110"][0] \
        == front


def test_filename_case_does_not_decide_whether_a_photo_is_found(tmp_path,
                                                                monkeypatch):
    """Windows and the WebDAV mount are both case-insensitive, so a set
    membership test on the raw listing missed a file that differed only in
    case — it was there, and the style was reported as having none."""
    primary = tmp_path / "primary"; primary.mkdir()
    monkeypatch.setattr(shared, "EXTRACTED_IMAGES_DIR", str(tmp_path / "none"))
    (primary / "dr5108_FRONT.png").write_bytes(_png())

    assert shared.load_style_photo_map(["DR5108"], str(primary))["DR5108"][0] \
        is not None
