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
