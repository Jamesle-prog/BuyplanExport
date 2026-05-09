"""Test ProgressLookup three-tier contract number resolution."""
import os
import tempfile
import pytest
import pandas as pd


@pytest.fixture
def sample_progress_xlsx():
    """Create a temporary 大货进度表 Excel file for testing."""
    tmpdir = tempfile.mkdtemp()
    filepath = os.path.join(tmpdir, "progress_test.xlsx")

    # Create sample data with:
    # - Same (style, color) appearing under different POs → different contracts
    # - Various normalization cases
    data = {
        "序号": [1, 2, 3, 4, 5, 6, 7, 8],
        "合同号": [
            "26301-ZA7001",  # Row 1: PO=500001, DR4532, NAVY
            "26302-ZA7002",  # Row 2: PO=500002, DR4532, NAVY (SAME style/color, DIFF contract)
            "26303-ZA7003",  # Row 3: PO=500003, DR4532, NAVY (3rd occurrence)
            "26304-ZA7004",  # Row 4: PO=500004, DR5000, BLACK
            "26305-ZA7005",  # Row 5: PO=500005, DR6000, (blank color)
            "26306-ZA7006",  # Row 6: PO=500006, ST1000, NAVY (different style, same color)
            "26307-ZA7007",  # Row 7: blank PO, DR7000, RED
            "26308-ZA7008",  # Row 8: blank PO, DR8000, BLUE
        ],
        "所在PO": ["HHPPC038", "HHPPC039", "HHPPC040", "HHPPC041", "", "", "", ""],
        "IMAGE": ["", "", "", "", "", "", "", ""],
        "款式": [
            "DR4532",      # Row 1-3: same style
            "DR4532",
            "DR4532",
            "DR5000",      # Row 4: different style
            "DR6000",      # Row 5: different style
            "ST1000",      # Row 6: different style (hyphen will be normalized away)
            "DR7000",      # Row 7: no PO
            "DR8000",      # Row 8: no PO
        ],
        "颜色": [
            "52# NAVY",    # Row 1-3: same color (numeric prefix to strip)
            "52# NAVY",
            "52# NAVY",
            "2# BLACK",    # Row 4: different color
            "",            # Row 5: blank color
            "NAVY",        # Row 6: no prefix (should normalize to NAVY)
            "RED",         # Row 7: no normalization needed
            "8# BLUE",     # Row 8: numeric prefix
        ],
        "主标颜色": ["", "", "", "", "", "", "", ""],
        "PO离厂日期": ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-04", "", "", "", ""],
        "数量": [100, 200, 150, 300, 50, 120, 80, 60],
        "PO#": [
            "500001",  # Row 1: unique PO
            "500002",  # Row 2: unique PO (but same style+color as row 1)
            "500003",  # Row 3: unique PO (but same style+color as rows 1-2)
            "500004",  # Row 4: unique PO
            "500005",  # Row 5: unique PO
            "500006",  # Row 6: unique PO
            "",        # Row 7: no PO
            "500008",  # Row 8: unique PO
        ],
        "BRAND": ["Brand1", "Brand1", "Brand1", "Brand2", "Brand3", "Brand1", "Brand1", "Brand1"],
        "FABRICDETAIL": ["Fabric1", "Fabric1", "Fabric1", "Fabric2", "", "Fabric1", "", ""],
    }

    df = pd.DataFrame(data)
    df.to_excel(filepath, sheet_name="2026 Zalando", index=False)

    return filepath


def test_progress_lookup_primary_key_po_style_color_code(sample_progress_xlsx):
    """Test primary (po, style, color_code) lookup — most specific with factory dye-lot code."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # With color_code (when available), even more specific matching
    # Rows have color_code from the lookup table
    assert pl.get_contract_no("DR4532", "52# NAVY", "500001", "") == "26301-ZA7001"
    assert pl.get_contract_no("DR4532", "52# NAVY", "500002", "") == "26302-ZA7002"


def test_progress_lookup_primary_key_po_style_color(sample_progress_xlsx):
    """Test (po, style, color) lookup — handles same style+color with different POs."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # Row 1: PO=500001, style=DR4532, color=NAVY → 26301-ZA7001
    # Row 2: PO=500002, style=DR4532, color=NAVY → 26302-ZA7002 (same style+color, DIFFERENT contract)
    # Row 3: PO=500003, style=DR4532, color=NAVY → 26303-ZA7003 (same style+color, DIFFERENT contract)

    # With (PO, style, color) lookup, each PO gets the right contract
    assert pl.get_contract_no("DR4532", "52# NAVY", "500001") == "26301-ZA7001"
    assert pl.get_contract_no("DR4532", "52# NAVY", "500002") == "26302-ZA7002"
    assert pl.get_contract_no("DR4532", "52# NAVY", "500003") == "26303-ZA7003"


def test_progress_lookup_fallback_style_color(sample_progress_xlsx):
    """Test fallback (style, color) lookup when PO not available."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # No PO provided: should return first matching (style, color) record
    # For DR4532/NAVY, first is 26301-ZA7001 (from row 1)
    assert pl.get_contract_no("DR4532", "NAVY", "") == "26301-ZA7001"
    assert pl.get_contract_no("DR5000", "BLACK", "") == "26304-ZA7004"


def test_progress_lookup_fallback_style_only(sample_progress_xlsx):
    """Test fallback style-only lookup when color not available."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # DR6000 has blank color in the table; lookup with empty color should still find it
    # via style-only fallback
    cno = pl.get_contract_no("DR6000", "", "")
    assert cno == "26305-ZA7005"


def test_progress_lookup_normalization_style(sample_progress_xlsx):
    """Test style normalization: dashes, spaces, lowercase → uppercase, no-dash."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # All these should match "DR4532" in the table
    assert pl.get_contract_no("DR-4532", "NAVY", "") == "26301-ZA7001"  # dash
    assert pl.get_contract_no("dr4532", "NAVY", "") == "26301-ZA7001"    # lowercase
    assert pl.get_contract_no("DR 4532", "NAVY", "") == "26301-ZA7001"   # space


def test_progress_lookup_normalization_color(sample_progress_xlsx):
    """Test color normalization: strip numeric prefix, lowercase → uppercase."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # All these should match "NAVY" (after stripping "52#")
    assert pl.get_contract_no("DR4532", "52# NAVY", "") == "26301-ZA7001"     # with prefix
    assert pl.get_contract_no("DR4532", "NAVY", "") == "26301-ZA7001"         # no prefix
    assert pl.get_contract_no("DR4532", "navy", "") == "26301-ZA7001"         # lowercase
    assert pl.get_contract_no("DR4532", "52#NAVY", "") == "26301-ZA7001"      # no space


def test_progress_lookup_normalization_po(sample_progress_xlsx):
    """Test PO normalization: dashes, spaces, lowercase."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # All these should match PO "500001"
    assert pl.get_contract_no("DR4532", "NAVY", "500001") == "26301-ZA7001"
    assert pl.get_contract_no("DR4532", "NAVY", "500-001") == "26301-ZA7001"  # dash
    assert pl.get_contract_no("DR4532", "NAVY", "500 001") == "26301-ZA7001"  # space


def test_progress_lookup_empty_inputs(sample_progress_xlsx):
    """Test edge cases: empty style, color, PO."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # Empty style → no match
    assert pl.get_contract_no("", "NAVY", "500001") == ""

    # Empty everything → no match
    assert pl.get_contract_no("", "", "") == ""


def test_progress_lookup_get_image_id(sample_progress_xlsx):
    """Test get_image_id with three-tier fallback."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # All rows have empty image_id, so should return "" for any lookup
    assert pl.get_image_id("DR4532", "NAVY", "500001") == ""
    assert pl.get_image_id("DR5000", "BLACK", "") == ""


def test_progress_lookup_get_record(sample_progress_xlsx):
    """Test get_record returns full dict."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # Get full record with (PO, style, color)
    rec = pl.get_record("DR4532", "NAVY", "500001")
    assert rec is not None
    assert rec["contract_no"] == "26301-ZA7001"
    assert rec["zalando_po"] == "500001"

    # Different PO → different record
    rec2 = pl.get_record("DR4532", "NAVY", "500002")
    assert rec2 is not None
    assert rec2["contract_no"] == "26302-ZA7002"
    assert rec2["zalando_po"] == "500002"


def test_progress_lookup_no_duplicate_preference(sample_progress_xlsx):
    """Verify that (PO, style, color) returns the exact record, not just the first."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # Without PO, (style, color) returns first record (row 1)
    cno_no_po = pl.get_contract_no("DR4532", "NAVY", "")
    assert cno_no_po == "26301-ZA7001"

    # With PO=500003, should return row 3, not row 1
    cno_with_po = pl.get_contract_no("DR4532", "NAVY", "500003")
    assert cno_with_po == "26303-ZA7003"
    assert cno_with_po != cno_no_po  # Verify they're different


def test_progress_lookup_get_all_for_style(sample_progress_xlsx):
    """Test get_all_for_style returns all color rows for a style."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # DR4532 appears in rows 1-3 (all with NAVY color)
    all_rows = pl.get_all_for_style("DR4532")
    assert len(all_rows) == 3
    assert all(r["style"] == "DR4532" for r in all_rows)


def test_progress_lookup_all_styles(sample_progress_xlsx):
    """Test all_styles returns unique normalized style keys."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    styles = pl.all_styles()
    assert "DR4532" in styles
    assert "DR5000" in styles
    assert "DR6000" in styles
    assert "ST1000" in styles
    assert "DR7000" in styles
    assert "DR8000" in styles


def test_extract_color_code():
    """Test _extract_color_code extracts numeric color codes correctly."""
    from po_extractor.lookups.progress_lookup import _extract_color_code

    # Leading prefix
    assert _extract_color_code("52# NAVY") == "52"
    assert _extract_color_code("2# BLACK") == "2"
    assert _extract_color_code("58#蓝色") == "58"
    # Trailing suffix
    assert _extract_color_code("NAVY 52#") == "52"
    assert _extract_color_code("BURGUNDY #74") == "74"
    # Edge cases
    assert _extract_color_code("NAVY") == ""           # no code
    assert _extract_color_code("") == ""               # empty
    assert _extract_color_code("  52# NAVY  ") == "52" # leading whitespace


def test_clean_cn_color():
    """Test _clean_cn_color strips numeric prefix from Chinese color names."""
    from po_extractor.lookups.progress_lookup import _clean_cn_color

    assert _clean_cn_color("58#浅蓝") == "浅蓝"
    assert _clean_cn_color("72# 蓝色") == "蓝色"
    assert _clean_cn_color("#58 浅蓝") == "浅蓝"
    assert _clean_cn_color("浅蓝") == "浅蓝"      # already clean
    assert _clean_cn_color("浅蓝 58#") == "浅蓝"
    assert _clean_cn_color("") == ""
    assert _clean_cn_color(None) == ""


def test_progress_lookup_returns_cn_color():
    """Test that get_cn_color and get_color_code work after loading from xlsx."""
    import os, tempfile
    import pandas as pd
    from po_extractor.lookups import ProgressLookup

    tmpdir = tempfile.mkdtemp()
    filepath = os.path.join(tmpdir, "progress_cn.xlsx")

    # Sample data with 中文颜色 and 中文颜色代码 columns
    data = {
        "序号": [1, 2],
        "合同号": ["26302-ZA7099", "26302-ZA7100"],
        "所在PO": ["HHPPC041", "HHPPC042"],
        "IMAGE": ["", ""],
        "款式": ["DR4424", "DR4425"],
        "测试": ["", ""],
        "英文颜色": ["blue", "navy"],
        "主标颜色": ["黑色", "黑色"],
        "中文颜色": ["58#浅蓝", "52#深蓝"],   # with numeric prefix
        "中文颜色代码": ["58", "52"],
        "PO离厂日期": ["", ""],
        "数量": [400, 300],
        "PO#": ["", ""],
        "BRAND": ["Anna Field", "Anna Field"],
        "FABRICDETAIL": ["", ""],
    }
    pd.DataFrame(data).to_excel(filepath, sheet_name="2026 Zalando", index=False)
    pl = ProgressLookup(filepath)

    # Verify cn_color is stripped of numeric prefix and the explicit code is used
    assert pl.get_cn_color("DR4424", "blue", pc_no="HHPPC041") == "浅蓝"
    assert pl.get_color_code("DR4424", "blue", pc_no="HHPPC041") == "58"
    assert pl.get_label_color("DR4424", "blue", pc_no="HHPPC041") == "黑色"

    # Different style → different match
    assert pl.get_cn_color("DR4425", "navy", pc_no="HHPPC042") == "深蓝"
    assert pl.get_color_code("DR4425", "navy", pc_no="HHPPC042") == "52"

    # Not found → empty string
    assert pl.get_cn_color("UNKNOWN", "x", pc_no="HHPPC999") == ""


def test_clean_color_for_lookup_returns_steps():
    """Test clean_color_for_lookup returns the cleaned value AND a step log."""
    from po_extractor.lookups.progress_lookup import clean_color_for_lookup

    # Lowercase only — single step
    cleaned, steps = clean_color_for_lookup("blue")
    assert cleaned == "BLUE"
    assert "uppercased" in steps[0]
    assert len(steps) == 1

    # Leading code
    cleaned, steps = clean_color_for_lookup("52# NAVY")
    assert cleaned == "NAVY"
    assert any("stripped leading code" in s and "52#" in s for s in steps)

    # Trailing code
    cleaned, steps = clean_color_for_lookup("NAVY 52#")
    assert cleaned == "NAVY"
    assert any("stripped trailing code" in s for s in steps)

    # Hash-prefix code
    cleaned, steps = clean_color_for_lookup("BURGUNDY #74")
    assert cleaned == "BURGUNDY"
    assert any("stripped trailing code" in s for s in steps)

    # Chinese characters stripped
    cleaned, steps = clean_color_for_lookup("BLACK 黑色")
    assert cleaned == "BLACK"
    assert any("removed non-ASCII" in s for s in steps)

    # Newlines collapsed
    cleaned, steps = clean_color_for_lookup("BLACK\n黑色")
    assert cleaned == "BLACK"
    assert any("collapsed whitespace" in s or "newlines" in s for s in steps)

    # Combined cleanup — multiple steps
    cleaned, steps = clean_color_for_lookup("52# NAVY\n深蓝")
    assert cleaned == "NAVY"
    assert len(steps) >= 2

    # Already clean — no steps
    cleaned, steps = clean_color_for_lookup("NAVY")
    assert cleaned == "NAVY"
    assert steps == []

    # Empty input
    cleaned, steps = clean_color_for_lookup("")
    assert cleaned == ""
    assert steps == []


def test_normalise_color_messy_inputs():
    """Test _normalise_color handles real-world messy color values."""
    from po_extractor.lookups.progress_lookup import _normalise_color

    # Case + numeric prefix
    assert _normalise_color("52# NAVY") == "NAVY"
    assert _normalise_color("blue") == "BLUE"

    # Trailing numeric code
    assert _normalise_color("NAVY 52#") == "NAVY"
    assert _normalise_color("BURGUNDY #74") == "BURGUNDY"

    # Chinese annotations stripped
    assert _normalise_color("BLACK 黑色") == "BLACK"
    assert _normalise_color("NAVY深蓝") == "NAVY"

    # Newlines collapsed
    assert _normalise_color("BLACK\n黑色") == "BLACK"
    assert _normalise_color("DK GREY\n") == "DK GREY"

    # Mixed (newline + Chinese + trailing code)
    assert _normalise_color("CREAM 87#\n奶白色") == "CREAM"

    # Multi-word colors preserved
    assert _normalise_color("DARK TEAL") == "DARK TEAL"
    assert _normalise_color("Cream/navy piping") == "CREAM/NAVY PIPING"

    # Edge cases
    assert _normalise_color("") == ""
    assert _normalise_color(None) == ""


def test_progress_lookup_fallback_style_code(sample_progress_xlsx):
    """Test (style, color_code) fallback when color_name doesn't match."""
    from po_extractor.lookups import ProgressLookup

    pl = ProgressLookup(sample_progress_xlsx)

    # Row 1 has color "52# NAVY" → color_code="52", color_norm="NAVY"
    # Look up with code only (passing wrong color_name "FOOBAR" so name lookup fails,
    # but code "52" should match)
    cno = pl.get_contract_no("DR4532", "FOOBAR", "", "52")
    assert cno == "26301-ZA7001"  # First DR4532 row with code 52

    # Row 4 has color "2# BLACK" → color_code="2"
    cno = pl.get_contract_no("DR5000", "WRONG", "", "2")
    assert cno == "26304-ZA7004"


def test_progress_lookup_primary_pc_no():
    """Test PRIMARY (pc_no, style, color) lookup — the most reliable join key.

    Uses Sky East PC No (所在PO col 2) which is reliably populated in 大货进度表,
    unlike PO# (col 12) which is often blank.
    """
    import os, tempfile
    import pandas as pd
    from po_extractor.lookups import ProgressLookup

    tmpdir = tempfile.mkdtemp()
    filepath = os.path.join(tmpdir, "progress_pc_test.xlsx")

    # Two rows with same style+color but DIFFERENT PC No — PO# blank in both
    # (mimics the real 大货进度表 where 所在PO is filled but PO# is empty)
    data = {
        "序号": [1, 2],
        "合同号": ["26302-ZA7038", "26302-ZA7087"],
        "所在PO": ["HHPPC032", "HHPPC040"],     # ← KEY: different PCs
        "IMAGE": ["", ""],
        "款式": ["ZLD060/S24DTR003", "ZLD060/S24DTR003"],
        "颜色": ["BLACK", "BLACK"],             # SAME color
        "主标颜色": ["", ""],
        "PO离厂日期": ["", ""],
        "数量": [1500, 1200],
        "PO#": ["", ""],                         # ← BLANK (real-world case)
        "BRAND": ["Brand1", "Brand1"],
        "FABRICDETAIL": ["", ""],
    }
    pd.DataFrame(data).to_excel(filepath, sheet_name="2026 Zalando", index=False)
    pl = ProgressLookup(filepath)

    # Without pc_no, falls back to (style, color) → first match (WRONG row)
    cno_no_pc = pl.get_contract_no("ZLD060/S24DTR003", "BLACK", "")
    assert cno_no_pc == "26302-ZA7038"  # First match

    # WITH pc_no=HHPPC040 → should find the CORRECT contract
    cno_with_pc = pl.get_contract_no(
        "ZLD060/S24DTR003", "BLACK", "", pc_no="HHPPC040")
    assert cno_with_pc == "26302-ZA7087"

    # WITH pc_no=HHPPC032 → finds the OTHER contract
    cno_other_pc = pl.get_contract_no(
        "ZLD060/S24DTR003", "BLACK", "", pc_no="HHPPC032")
    assert cno_other_pc == "26302-ZA7038"


def test_progress_lookup_pc_style_fallback_when_color_messy():
    """Test (pc_no, style) fallback when color value can't be matched."""
    import os, tempfile
    import pandas as pd
    from po_extractor.lookups import ProgressLookup

    tmpdir = tempfile.mkdtemp()
    filepath = os.path.join(tmpdir, "progress_pc_style.xlsx")

    # 大货进度表 has messy color "BLACK 2#\n黑色 ☆要黑色"
    # Sky East item asks for plain "PINK" — won't match by color, but PC+style
    # should still resolve correctly
    data = {
        "序号": [1],
        "合同号": ["26302-ZA7099"],
        "所在PO": ["HHPPC050"],
        "IMAGE": [""],
        "款式": ["DR9999"],
        "颜色": ["UNRECOGNIZABLE_COLOR_VALUE"],
        "主标颜色": [""],
        "PO离厂日期": [""],
        "数量": [100],
        "PO#": [""],
        "BRAND": ["Brand1"],
        "FABRICDETAIL": [""],
    }
    pd.DataFrame(data).to_excel(filepath, sheet_name="2026 Zalando", index=False)
    pl = ProgressLookup(filepath)

    # Color won't match, but pc_no=HHPPC050 + style=DR9999 is unique
    cno = pl.get_contract_no(
        "DR9999", "PINK_THAT_DOESNT_MATCH", "", pc_no="HHPPC050")
    assert cno == "26302-ZA7099"


def test_build_cn_lookup():
    """build_cn_lookup returns a dict keyed by (company, brand, en_color_norm)."""
    import os, tempfile
    import pandas as pd
    from po_extractor.lookups import ProgressLookup

    tmpdir = tempfile.mkdtemp()
    filepath = os.path.join(tmpdir, "progress_cn.xlsx")

    # Progress file has 中文颜色 and 主标颜色 columns
    data = {
        "序号":        [1, 2, 3],
        "合同号":      ["C001", "C002", "C003"],
        "所在PO":      ["PC001", "PC002", "PC003"],
        "IMAGE":       ["", "", ""],
        "款式":        ["DR1000", "DR2000", "DR3000"],
        "颜色":        ["58# LIGHT BLUE", "NAVY", "BLACK"],
        "主标颜色":    ["浅蓝", "深蓝", "黑色"],
        "中文颜色":    ["浅蓝", "藏青色", "黑色"],
        "中文颜色代码": ["58", "52", "2"],
        "PO离厂日期":  ["", "", ""],
        "数量":        [100, 200, 300],
        "PO#":         ["", "", ""],
        "BRAND":       ["BrandA", "BrandA", "BrandB"],
        "FABRICDETAIL": ["", "", ""],
    }
    pd.DataFrame(data).to_excel(filepath, sheet_name="2026 Zalando", index=False)
    pl = ProgressLookup(filepath)

    COMPANY = "SkyEast"
    cn_lookup = pl.build_cn_lookup(COMPANY)

    # Cleaned color "LIGHT BLUE" should be a key (numeric prefix stripped)
    assert cn_lookup.get((COMPANY, "BrandA", "Light Blue")) == "浅蓝"
    # Raw color "58# LIGHT BLUE" title-cased should also be a key
    assert cn_lookup.get((COMPANY, "BrandA", "58# Light Blue")) == "浅蓝"
    # Plain color
    assert cn_lookup.get((COMPANY, "BrandA", "Navy")) == "藏青色"
    assert cn_lookup.get((COMPANY, "BrandB", "Black")) == "黑色"
    # Unknown brand+color → missing
    assert cn_lookup.get((COMPANY, "BrandA", "Red")) is None


def test_build_label_lookup():
    """build_label_lookup returns a dict keyed by (company, brand, en_color_norm)."""
    import os, tempfile
    import pandas as pd
    from po_extractor.lookups import ProgressLookup

    tmpdir = tempfile.mkdtemp()
    filepath = os.path.join(tmpdir, "progress_label.xlsx")

    data = {
        "序号":        [1, 2],
        "合同号":      ["C001", "C002"],
        "所在PO":      ["PC001", "PC002"],
        "IMAGE":       ["", ""],
        "款式":        ["ST1000", "ST2000"],
        "颜色":        ["52# NAVY", "RED"],
        "主标颜色":    ["深蓝", "红色"],
        "中文颜色":    ["藏青色", "红色"],
        "中文颜色代码": ["52", ""],
        "PO离厂日期":  ["", ""],
        "数量":        [100, 200],
        "PO#":         ["", ""],
        "BRAND":       ["BrandX", "BrandX"],
        "FABRICDETAIL": ["", ""],
    }
    pd.DataFrame(data).to_excel(filepath, sheet_name="2026 Zalando", index=False)
    pl = ProgressLookup(filepath)

    COMPANY = "SkyEast"
    label_lookup = pl.build_label_lookup(COMPANY)

    # Cleaned color "NAVY" title-cased → key "Navy"
    assert label_lookup.get((COMPANY, "BrandX", "Navy")) == "深蓝"
    # Raw color "52# NAVY" title-cased → key "52# Navy"
    assert label_lookup.get((COMPANY, "BrandX", "52# Navy")) == "深蓝"
    assert label_lookup.get((COMPANY, "BrandX", "Red")) == "红色"
    # Row with empty label_color should not appear
    assert label_lookup.get((COMPANY, "BrandX", "Green")) is None
