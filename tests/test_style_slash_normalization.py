"""A style number's "/" is stored, matched and searched as "_".

Client files carry the same style both ways — ``TP3267-3/4SLV`` (a 3/4
sleeve) in the contract, ``TP3267-3_4SLV`` everywhere a filename was
involved, because Windows filenames cannot hold "/". Stored raw, the two
spellings are different strings: fabric-mapping joins missed, search boxes
found one and not the other, the photo existed but never matched. Rule since
2026-08-31: one spelling — "_" — normalised at intake, migrated on disk.
"""
from __future__ import annotations

import sqlite3

import pytest

from po_extractor.utils.style_norm import normalize_style_no


# ── the helper itself ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("TP3267-3/4SLV", "TP3267-3_4SLV"),
    ("ZLD060/S24DTR003", "ZLD060_S24DTR003"),
    ("A/B/C", "A_B_C"),
    ("A\\B", "A_B"),                       # backslash too — same filename rule
    ("  PLAIN123  ", "PLAIN123"),
    ("ALREADY_OK", "ALREADY_OK"),
])
def test_slash_becomes_underscore(raw, expected):
    assert normalize_style_no(raw) == expected


def test_none_and_non_strings_pass_through():
    """POMetadata.style is Optional — None must stay None, never 'None'."""
    assert normalize_style_no(None) is None
    assert normalize_style_no(123) == 123


# ── every parser is covered at the model, by construction ───────────────────

def test_size_row_normalizes_on_construction():
    from po_extractor.models.po_data import SizeRow
    r = SizeRow("PO1", "TP3267-3/4SLV", "BLK", "M", 10, "700000000001")
    assert r.style == "TP3267-3_4SLV"


def test_po_metadata_normalizes_and_keeps_none():
    from po_extractor.models.po_data import POMetadata
    assert POMetadata(po_number="P1", style="A/B").style == "A_B"
    assert POMetadata(po_number="P1").style is None


def test_sky_east_item_normalizes_style_only():
    """config_sku, colours and fabric codes keep their slashes — only the
    style is a filename-keyed lookup key."""
    from po_extractor.models.sky_east_data import SkyEastItem
    item = SkyEastItem(
        pc_no="PC1", zalando_po="PO1", style="TP3267-3/4SLV",
        config_sku="AN6/21C", article_name="A", brand="B",
        color_name="BLK/WHT", colour_code="Q11", launch_date="",
        fabric_item_no="HHP-JS/1", fabrication="", contract_no="",
        sizes={"S": 1}, total_qty=1, fob_usd=1.0, total_cost_usd=1.0)
    assert item.style == "TP3267-3_4SLV"
    assert item.config_sku == "AN6/21C"
    assert item.color_name == "BLK/WHT"
    assert item.fabric_item_no == "HHP-JS/1"


# ── the store writes that bypass the models ─────────────────────────────────

def test_fabric_mapping_upload_stores_the_underscore_spelling(tmp_path):
    from po_extractor.store.po_store import POStore
    from po_extractor.models.fabric_part import FabricPart

    s = POStore(str(tmp_path / "t.db"))
    s.save_fabric_parts(
        "sky_east", "ZLD060/S24DTR003",
        [FabricPart(seq=1, body_part="主面料", hhn_no="HHP-JS-1",
                    composition="100% PL", weight_gsm=180, width_cm=150)])
    assert s.list_mapped_styles("sky_east") == {"ZLD060_S24DTR003"}


def test_mapping_saved_with_slash_is_found_by_a_po_parsed_with_slash(tmp_path):
    """The whole point end to end: file A wrote the mapping with a slash,
    file B's PO carries the same slash — the join must land."""
    from po_extractor.store.po_store import POStore
    from po_extractor.models.fabric_part import FabricPart

    s = POStore(str(tmp_path / "t.db"))
    s.save_fabric_parts(
        "sky_east", "TP3267-3/4SLV",
        [FabricPart(seq=1, body_part="主面料", hhn_no="HHP-1",
                    composition="", weight_gsm=0, width_cm=0)])
    got = s.load_fabric_parts_for_styles(
        [normalize_style_no("TP3267-3/4SLV")], source="sky_east")
    assert "TP3267-3_4SLV" in got and got["TP3267-3_4SLV"]


def test_production_tracking_keys_on_the_underscore_spelling(tmp_path):
    from po_extractor.store.production_tracking_store import ProductionTrackingStore

    s = ProductionTrackingStore(str(tmp_path / "t.db"))
    s.upsert(po_number="PO1", style="ZLD060/S24DTR003", factory="F1",
             company="GIII", overall_notes="", use_substitute_materials=0,
             stage_fields={}, dep_fields={}, qc_fields={}, updated_by="t")
    recs = s.list_all(allow_all=True)
    assert [r["style"] for r in recs] == ["ZLD060_S24DTR003"]

    # A second save with the OTHER spelling updates the same record — the
    # two spellings must never become two tracking rows again.
    s.upsert(po_number="PO1", style="ZLD060_S24DTR003", factory="F2",
             company="GIII", overall_notes="", use_substitute_materials=0,
             stage_fields={}, dep_fields={}, qc_fields={}, updated_by="t")
    recs = s.list_all(allow_all=True)
    assert len(recs) == 1 and recs[0]["factory"] == "F2"


def test_fabric_consumption_normalizes(tmp_path):
    from po_extractor.store.po_store import POStore
    s = POStore(str(tmp_path / "t.db"))
    s.save_fabric_consumption([{"style": "A/B", "cons_kg": 1.5}])
    assert "A_B" in s.load_fabric_consumption(["A_B"])


# ── what is already on disk is migrated ─────────────────────────────────────

def _old_db_with_slashes(path) -> None:
    """A pre-migration database: slash styles in several tables, plus a
    UNIQUE-collision twin in production_tracking."""
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE po_size_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT, po_number TEXT NOT NULL,
            style TEXT, color TEXT, size TEXT, units INTEGER, upc TEXT,
            xfty_date TEXT DEFAULT '', extracted_at TEXT,
            UNIQUE(po_number, style, color, size, xfty_date));
        INSERT INTO po_size_rows (po_number, style, color, size, units, upc)
            VALUES ('PO1', 'TP3267-3/4SLV', 'BLK', 'M', 5, '1');
        CREATE TABLE production_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT, po_number TEXT, style TEXT,
            factory TEXT, UNIQUE(po_number, style));
        INSERT INTO production_tracking (po_number, style, factory)
            VALUES ('PO2', 'ZLD060/S24DTR003', 'OLD'),
                   ('PO2', 'ZLD060_S24DTR003', 'NEW');
    """)
    conn.commit()
    conn.close()


def test_migration_normalizes_existing_rows_and_survives_a_twin(tmp_path):
    from po_extractor.store.po_store import POStore

    db = tmp_path / "old.db"
    _old_db_with_slashes(db)
    POStore(str(db))          # opening runs the sweep

    conn = sqlite3.connect(str(db))
    assert conn.execute(
        "SELECT style FROM po_size_rows").fetchone()[0] == "TP3267-3_4SLV"
    # the collision pair: the twin is untouched, the slash row is kept as-is
    # (skipped, not deleted) — nothing lost, nothing crashed
    rows = sorted(r[0] for r in conn.execute(
        "SELECT factory FROM production_tracking"))
    assert rows == ["NEW", "OLD"]
    conn.close()


def test_migration_is_idempotent(tmp_path):
    from po_extractor.store.po_store import POStore
    db = tmp_path / "old.db"
    _old_db_with_slashes(db)
    POStore(str(db))
    POStore(str(db))          # a second open must change nothing and not raise
    conn = sqlite3.connect(str(db))
    assert conn.execute(
        "SELECT COUNT(*) FROM po_size_rows").fetchone()[0] == 1
    conn.close()


# ── the processing log tells the user what was adjusted ─────────────────────

def test_collector_records_changes_only_while_active():
    from po_extractor.utils import style_norm as sn

    # inactive by default: normalizing records nothing and never raises
    sn.normalize_style_no("A/B")
    sn.begin_collecting_changes()
    sn.normalize_style_no("A/B")
    sn.normalize_style_no("A/B")          # duplicate — reported once
    sn.normalize_style_no("CLEAN")        # unchanged — not reported
    sn.normalize_style_no("C/D")
    assert sn.end_collecting_changes() == [("A/B", "A_B"), ("C/D", "C_D")]
    # the window is closed: a later call records nothing
    sn.normalize_style_no("E/F")
    assert sn.end_collecting_changes() == []


def test_collector_is_isolated_per_thread():
    """Two Streamlit sessions process files concurrently — one user's upload
    must never report another user's styles (same rule as audit_context)."""
    import threading
    from po_extractor.utils import style_norm as sn

    sn.begin_collecting_changes()
    seen_in_child: list = []

    def child():
        sn.normalize_style_no("X/Y")              # no window in THIS thread
        sn.begin_collecting_changes()
        sn.normalize_style_no("P/Q")
        seen_in_child.extend(sn.end_collecting_changes())

    th = threading.Thread(target=child)
    th.start(); th.join(timeout=10)
    assert not th.is_alive()
    assert seen_in_child == [("P/Q", "P_Q")]
    # the parent window saw none of the child's styles
    assert sn.end_collecting_changes() == []


def test_style_change_note_formats_and_escapes():
    from ui.log_markup import style_change_note

    assert style_change_note([]) is None
    note = style_change_note([("TP3267-3/4SLV", "TP3267-3_4SLV")])
    assert "TP3267-3/4SLV → TP3267-3_4SLV" in note
    assert note.startswith("🔤 1 style number(s) adjusted")
    # values come from uploaded files — markup in them must not survive
    hostile = style_change_note([("<b>/x", "<b>_x")])
    assert "<b>" not in hostile and "&lt;b&gt;" in hostile
