"""An upload must never overwrite a photo already in the library.

The image folder a user configures is their own curated photo library — often
a shared network drive maintained by hand. The bytes ``save_images_to_disk``
writes are only whatever the CLIENT embedded in their contract file, which can
be a different garment entirely.

Found 2026-09-01: ``TP3267-3_4SLV_front.png`` on the share was byte-for-byte
identical to the contract's embedded image (a sleeveless top) and carried that
upload's timestamp — the real 3/4-sleeve photo had been silently replaced, so
the wrong garment went onto the 核料 doc every time. The filename never
changed, so nothing looked wrong until someone compared the picture to the
style. A style with no photo yet still gets one; an existing photo is now
never touched.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

from ui.shared import save_images_to_disk           # noqa: E402


def test_an_existing_style_photo_is_never_overwritten(tmp_path):
    library = tmp_path / "photos"
    library.mkdir()
    curated = library / "ST1_front.png"
    curated.write_bytes(b"the real curated photo")

    save_images_to_disk(
        {"PID1": b"the client contract's embedded image"},
        {"ST1": ["PID1"]},
        img_dir=str(library),
    )

    assert curated.read_bytes() == b"the real curated photo"


def test_a_style_with_no_photo_yet_still_gets_one(tmp_path):
    """The feature still works where it helps — this is a guard, not a
    removal."""
    library = tmp_path / "photos"
    library.mkdir()

    save_images_to_disk(
        {"PID1": b"front bytes", "PID2": b"back bytes"},
        {"NEWSTYLE": ["PID1", "PID2"]},
        img_dir=str(library),
    )

    assert (library / "NEWSTYLE_front.png").read_bytes() == b"front bytes"
    assert (library / "NEWSTYLE_back.png").read_bytes() == b"back bytes"


def test_the_back_photo_is_protected_too(tmp_path):
    library = tmp_path / "photos"
    library.mkdir()
    (library / "ST1_back.png").write_bytes(b"curated back")

    save_images_to_disk(
        {"PID1": b"contract front", "PID2": b"contract back"},
        {"ST1": ["PID1", "PID2"]},
        img_dir=str(library),
    )

    assert (library / "ST1_back.png").read_bytes() == b"curated back"
    # the front had no curated file, so it is written
    assert (library / "ST1_front.png").read_bytes() == b"contract front"


def test_a_style_with_a_slash_writes_the_filename_form(tmp_path):
    """Styles keep "/" in the data (v2.143.0); a filename cannot, so the
    photo copy uses "_" — and is still protected once it exists."""
    library = tmp_path / "photos"
    library.mkdir()

    save_images_to_disk({"PID1": b"first"}, {"TP3267-3/4SLV": ["PID1"]},
                        img_dir=str(library))
    assert (library / "TP3267-3_4SLV_front.png").read_bytes() == b"first"

    save_images_to_disk({"PID1": b"second upload, different garment"},
                        {"TP3267-3/4SLV": ["PID1"]}, img_dir=str(library))
    assert (library / "TP3267-3_4SLV_front.png").read_bytes() == b"first"


# ── the library is read-only to us, and always outranks the fallback ────────

def test_the_sky_east_upload_never_writes_to_the_configured_library():
    """Directive 2026-09-01: 永远不要覆盖原始文件夹里的照片，自动提取的
    照片放在新的文件夹里. The pipeline must save extracted images ONLY to
    EXTRACTED_IMAGES_DIR — a call with no img_dir would land in the user's
    own library."""
    import inspect
    import ui.sky_east.processing as proc

    src = inspect.getsource(proc._run_sky_east_processing)
    calls = src.count("save_images_to_disk(")
    assert calls == 1, f"expected exactly one save call, found {calls}"
    assert "img_dir=EXTRACTED_IMAGES_DIR" in src


@pytest.fixture
def two_folders(tmp_path, monkeypatch):
    """A configured library + the extracted-images fallback, both scratch."""
    import ui.shared as sh
    library = tmp_path / "library"
    library.mkdir()
    fallback = tmp_path / "extracted"
    fallback.mkdir()
    monkeypatch.setattr(sh, "EXTRACTED_IMAGES_DIR", str(fallback))
    monkeypatch.setattr(sh, "PHOTO_CACHE_DIR", str(tmp_path / "cache"))
    return sh, library, fallback


def test_a_bare_named_library_photo_beats_a_front_named_extracted_one(two_folders):
    """The priority bug behind the wrong garment: candidate name used to be
    the outer loop, so "{style}_front.png" sitting in the extracted folder
    outranked the curated "{style}.png" in the library. The library must be
    searched to exhaustion first."""
    sh, library, fallback = two_folders
    (library / "ST1.png").write_bytes(b"curated")
    (fallback / "ST1_front.png").write_bytes(b"from the client contract")

    got = sh.load_style_photo_map(["ST1"], str(library))
    assert got["ST1"][0] == b"curated"

    front, _back = sh.load_style_photo_pair("ST1", str(library))
    assert front == b"curated"


def test_the_fallback_is_used_when_the_library_has_nothing(two_folders):
    """It is a fallback, not a ban — a style the library has no photo for
    still gets the extracted image."""
    sh, library, fallback = two_folders
    (fallback / "ST2_front.png").write_bytes(b"extracted")

    got = sh.load_style_photo_map(["ST2"], str(library))
    assert got["ST2"][0] == b"extracted"

    front, _back = sh.load_style_photo_pair("ST2", str(library))
    assert front == b"extracted"


def test_a_spaced_library_photo_still_beats_the_extracted_one(two_folders):
    """The canonical (space-tolerant) layer must also stay inside the
    per-folder search — a hand-typed library name outranks the fallback."""
    sh, library, fallback = two_folders
    (library / "TP3267-3_4 SLV.png").write_bytes(b"curated spaced")
    (fallback / "TP3267-3_4SLV_front.png").write_bytes(b"from the contract")

    got = sh.load_style_photo_map(["TP3267-3/4SLV"], str(library))
    assert got["TP3267-3/4SLV"][0] == b"curated spaced"
