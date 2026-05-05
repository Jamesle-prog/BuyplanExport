"""Regression tests for fabric-mapping row parser."""
from po_extractor.ui_helpers.fabric_mapping_parse import parse_fabric_mapping_rows


def test_empty_rows_returns_empty_dict():
    assert parse_fabric_mapping_rows([]) == {}


def test_header_only_returns_empty():
    rows = [("Style No.", "Fabric 1 Body Part", "Fabric 1 Code")]
    assert parse_fabric_mapping_rows(rows) == {}


def test_basic_parse_with_standard_layout():
    rows = [
        ("Style No.", "Fabric 1 Body Part", "Fabric 1 Code"),
        ("STY1", "Body", "HHN-001"),
        ("STY2", "Lining", "HHN-002"),
    ]
    result = parse_fabric_mapping_rows(rows)
    assert set(result.keys()) == {"STY1", "STY2"}
    assert len(result["STY1"]) == 1
    assert result["STY1"][0].hhn_no == "HHN-001"
    assert result["STY1"][0].body_part == "Body"
    assert result["STY1"][0].seq == 1


def test_multiple_fabric_slots_parsed():
    rows = [
        ("Style", "Fabric 1 BP", "Fabric 1 Code", "Fabric 2 BP", "Fabric 2 Code"),
        ("STY1", "Body", "HHN-A", "Lining", "HHN-B"),
    ]
    result = parse_fabric_mapping_rows(rows)
    parts = result["STY1"]
    assert len(parts) == 2
    assert parts[0].hhn_no == "HHN-A"
    assert parts[0].seq == 1
    assert parts[1].hhn_no == "HHN-B"
    assert parts[1].seq == 2


def test_skips_rows_without_hhn_code():
    """Slot with body_part but no code → not added to parts list."""
    rows = [
        ("Style", "Fabric 1 BP", "Fabric 1 Code"),
        ("STY1", "Body", ""),   # no code
    ]
    result = parse_fabric_mapping_rows(rows)
    # Style has no parts → not added to result
    assert "STY1" not in result


def test_skips_instruction_rows_starting_with_arrow():
    rows = [
        ("Style", "Fabric 1 Code"),
        ("↑ Replace example rows", "HHN-X"),
        ("STY1", "HHN-001"),
    ]
    result = parse_fabric_mapping_rows(rows)
    assert "STY1" in result
    assert "↑ Replace example rows" not in result


def test_skips_blank_style_rows():
    rows = [
        ("Style", "Fabric 1 Code"),
        (None, "HHN-001"),
        ("", "HHN-002"),
        ("STY1", "HHN-003"),
    ]
    result = parse_fabric_mapping_rows(rows)
    assert list(result.keys()) == ["STY1"]


def test_chinese_headers_work():
    rows = [
        ("款式号", "面料1部位", "面料1编号"),
        ("STY1", "主体", "HHN-CN-001"),
    ]
    result = parse_fabric_mapping_rows(rows)
    assert result["STY1"][0].hhn_no == "HHN-CN-001"
    assert result["STY1"][0].body_part == "主体"


def test_styles_stripped_of_whitespace():
    rows = [
        ("Style", "Fabric 1 Code"),
        ("  STY1  ", "HHN-001"),
    ]
    result = parse_fabric_mapping_rows(rows)
    assert "STY1" in result
    assert "  STY1  " not in result
