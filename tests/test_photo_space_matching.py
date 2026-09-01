"""A hand-typed photo filename still matches its style.

The photo share is maintained by hand, and the file for style
``TP3267-3_4SLV`` was saved as ``TP3267-3_4 SLV.png`` — one space. Exact
matching read that as "no photo", and the Sky East export silently fell back
to the image embedded in the client's contract file, putting the WRONG
garment on the generated 核料 document (found 2026-09-01, real order).

Matching is now canonical — case, spaces and punctuation don't count — with
the exact spelling always tried first so a properly named file can never be
displaced by a sloppier twin.
"""
from __future__ import annotations

import pytest


# ── the classifier used by the exporter-side folder walks ───────────────────

@pytest.mark.parametrize("stem,style,expected", [
    ("tp3267-3_4 slv",        "tp3267-3_4slv", "single"),   # the real case
    ("tp3267-3_4 slv_front",  "tp3267-3_4slv", "front"),
    ("tp3267-3_4 slv back",   "tp3267-3_4slv", "back"),
    ("tp3267 - 3_4slv",       "tp3267-3_4slv", "single"),   # spaces around dash
    ("tp3267-3_4slv",         "tp3267-3_4slv", "single"),   # exact still exact
    ("tp3267-3_4slv_front",   "tp3267-3_4slv", "front"),
])
def test_spaced_spellings_classify(stem, style, expected):
    from po_extractor.exporters._photo_utils import _classify_filename
    assert _classify_filename(stem, style) == expected


def test_a_longer_style_is_not_claimed_by_a_shorter_one():
    """Canonicalising eats separators, so the canonical layer must never
    accept a bare digit/letter suffix — TP30251 is a different style, not
    TP3025's front photo."""
    from po_extractor.exporters._photo_utils import _classify_filename
    assert _classify_filename("tp30251", "tp3025") is None
    assert _classify_filename("tp3025a", "tp3025") is None
    # while the classic separator forms keep working (legacy exact layer)
    assert _classify_filename("tp3025_1", "tp3025") == "front"
    assert _classify_filename("tp3025_b", "tp3025") == "back"


def test_resolve_photo_pair_finds_the_spaced_file():
    from po_extractor.exporters._photo_utils import resolve_photo_pair
    photo_map = {"TP3267-3_4 SLV.png": b"correct-front"}
    front, back = resolve_photo_pair("TP3267-3_4SLV", None, photo_map)
    assert front == b"correct-front" and back is None


# ── the UI-side folder lookups (Sky East buy plan path) ─────────────────────

@pytest.fixture
def folders(tmp_path, monkeypatch):
    """A primary photo folder + a diverted extracted-images fallback, so the
    test never touches the app's real data directory."""
    import ui.shared as sh
    primary = tmp_path / "photos"
    primary.mkdir()
    fallback = tmp_path / "extracted"
    fallback.mkdir()
    monkeypatch.setattr(sh, "EXTRACTED_IMAGES_DIR", str(fallback))
    monkeypatch.setattr(sh, "PHOTO_CACHE_DIR", str(tmp_path / "cache"))
    return sh, primary


def test_load_style_photo_map_finds_the_spaced_file(folders):
    sh, primary = folders
    (primary / "TP3267-3_4 SLV.png").write_bytes(b"correct-front")

    got = sh.load_style_photo_map(["TP3267-3_4SLV"], str(primary))
    assert "TP3267-3_4SLV" in got
    assert got["TP3267-3_4SLV"][0] == b"correct-front"


def test_exact_name_beats_a_canonical_twin(folders):
    """A properly named file must never be displaced by a sloppier spelling
    of the same canonical key."""
    sh, primary = folders
    (primary / "ST1.png").write_bytes(b"exact")
    (primary / "S T1.png").write_bytes(b"spaced")

    got = sh.load_style_photo_map(["ST1"], str(primary))
    assert got["ST1"][0] == b"exact"


def test_load_style_photo_pair_finds_the_spaced_file(folders):
    sh, primary = folders
    (primary / "TP3267-3_4 SLV_front.png").write_bytes(b"front!")
    (primary / "TP3267-3_4 SLV_back.png").write_bytes(b"back!")

    front, back = sh.load_style_photo_pair("TP3267-3_4SLV", str(primary))
    assert front == b"front!" and back == b"back!"


def test_no_photo_still_means_no_photo(folders):
    """The canonical layer must not conjure matches out of unrelated files."""
    sh, primary = folders
    (primary / "COMPLETELY-OTHER.png").write_bytes(b"x")
    assert sh.load_style_photo_map(["TP3267-3_4SLV"], str(primary)) == {}
