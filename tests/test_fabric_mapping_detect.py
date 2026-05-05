"""Regression tests for fabric-mapping header column detection."""
from po_extractor.ui_helpers.fabric_mapping_detect import (
    detect_fabric_mapping_columns,
)


def test_empty_header_falls_back_to_standard_layout():
    layout = detect_fabric_mapping_columns(())
    assert layout["style"] == 0
    assert len(layout["parts"]) == 4
    # Slot 1: BP=1, Code=2; Slot 2: BP=3, Code=4; ...
    assert layout["parts"][0] == {"body_part": 1, "code": 2}
    assert layout["parts"][3] == {"body_part": 7, "code": 8}


def test_detects_standard_english_headers():
    header = (
        "Style No.",
        "Fabric 1 Body Part", "Fabric 1 Code",
        "Fabric 2 Body Part", "Fabric 2 Code",
    )
    layout = detect_fabric_mapping_columns(header)
    assert layout["style"] == 0
    assert layout["parts"][0] == {"body_part": 1, "code": 2}
    assert layout["parts"][1] == {"body_part": 3, "code": 4}


def test_detects_chinese_headers():
    header = ("款式号", "面料1部位", "面料1编号", "面料2部位", "面料2编号")
    layout = detect_fabric_mapping_columns(header)
    assert layout["style"] == 0
    assert layout["parts"][0] == {"body_part": 1, "code": 2}
    assert layout["parts"][1] == {"body_part": 3, "code": 4}


def test_detects_code_only_slots():
    """Slots with code but no body part should still be emitted."""
    header = ("Style", "Fabric 1 Code", "Fabric 2 Code")
    layout = detect_fabric_mapping_columns(header)
    assert layout["style"] == 0
    assert len(layout["parts"]) == 2
    assert layout["parts"][0]["code"] == 1
    assert layout["parts"][0]["body_part"] is None
    assert layout["parts"][1]["code"] == 2


def test_drops_body_part_slots_without_code():
    """If only body_part exists for a slot (no code), slot is omitted."""
    header = ("Style", "Fabric 1 Body Part", "Fabric 2 Code")
    layout = detect_fabric_mapping_columns(header)
    # Slot 1 has BP only → dropped; Slot 2 has Code → kept
    assert all(p["code"] is not None for p in layout["parts"])
    assert any(p["code"] == 2 for p in layout["parts"])


def test_handles_supplier_article_number_alias():
    header = ("Supplier Article Number", "Fabric 1 Code")
    layout = detect_fabric_mapping_columns(header)
    assert layout["style"] == 0


def test_falls_back_when_no_code_columns():
    header = ("Brand", "Color", "Size")  # nothing recognisable
    layout = detect_fabric_mapping_columns(header)
    # Falls back to standard layout
    assert layout["style"] == 0
    assert len(layout["parts"]) == 4
