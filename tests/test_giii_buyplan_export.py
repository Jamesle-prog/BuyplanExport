"""Tests for the GIII buy-plan exporter (generated workbook)."""
from __future__ import annotations

import io

import openpyxl

from po_extractor.exporters.giii_buyplan_export import (
    BuyPlanHeader, BuyPlanRow, export_giii_buyplan,
)


def _rows():
    return [
        BuyPlanRow(contract_no="26502-DS3012", style="P6KH8FXB", po_number="DW867662UC",
                   cpo="", warehouse_code="UC", buyer="MY MACY'S",
                   color_en="NVY/NAVY", color_cn="藏青",
                   sizes={"S": 34, "M": 79, "L": 108}, ex_fty="46218",
                   packing_method="平装+衣架", is_prepack=False),
        BuyPlanRow(contract_no="26502-DS3012", style="P6KH8FXB", po_number="DW867662UC",
                   warehouse_code="UC", buyer="MY MACY'S",
                   color_en="QJC/CITY CLAY", color_cn="泥粉",
                   sizes={"S": 67, "M": 89, "L": 80}, ex_fty="46218",
                   packing_method="平装+衣架", is_prepack=False),
    ]


def _load(xlsx_bytes):
    return openpyxl.load_workbook(io.BytesIO(xlsx_bytes)).active


def _grid(ws):
    return [[c.value for c in row] for row in ws.iter_rows()]


def test_export_without_cprs_leaves_kb_columns_blank():
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear",
               supplier="新庄源", fabric="HB-XD6786", description="针织女套头衫"),
               _rows(), cprs=None))
    grid = _grid(ws)
    # Banner + title
    assert grid[0][0] == "江苏新万新服饰有限公司"
    assert "buy plan" in grid[1][0]
    # Header rows: row 8 (index 7) has 合同号; row 9 (index 8) has size letters
    assert grid[7][0] == "合同号"
    assert "S" in grid[8] and "M" in grid[8] and "L" in grid[8]
    # First data row (index 9): contract + style + PO
    assert grid[9][0] == "26502-DS3012"
    assert grid[9][1] == "P6KH8FXB"
    assert grid[9][4] == "UC"        # warehouse (already known)
    # CPRS columns (red sticker / carton mark / prepack ratio / pcs / msrp / rfid) blank
    # They are the last 8 columns; with no CPRS they must be blank/""
    last8 = grid[9][-8:]
    # red_sticker, carton_mark, packing, prepack(Y/N from PO), ratio, pcs, msrp, rfid
    assert last8[0] in ("", None)     # red sticker blank (no CPRS)
    assert last8[2] == "平装+衣架"    # packing method (PO)
    assert last8[3] == "N"            # prepack flag from PO (is_prepack=False)
    assert last8[4] in ("", None)     # prepack ratio blank
    assert last8[6] in ("", None)     # MSRP blank
    assert last8[7] in ("", None)     # RFID blank


def test_totals_and_color_subtotals():
    ws = _load(export_giii_buyplan(BuyPlanHeader(), _rows(), cprs=None))
    grid = _grid(ws)
    flat = [c for row in grid for c in row]
    assert "TTL" in flat
    # grand total 34+79+108 + 67+89+80 = 457
    assert 457 in flat
    # per-color subtotals present
    assert "藏青" in flat and "泥粉" in flat
    assert 221 in flat   # navy S+M+L = 34+79+108
    assert 236 in flat   # clay S+M+L = 67+89+80


class _MockCprs:
    """Fake CPRS /evaluate/po — decodes the raw PO to a UC warehouse and returns
    a representative result set (red sticker, carton mark, prepack ratio, pcs)."""
    _RED = {"domain": "carton", "subtype": "red_carton_sticker",
            "status": "confirmed", "resultJson": {"code": "MY"}}

    def evaluate_po(self, raw):
        brand = str(raw.get("brand", "")).strip()
        if not brand:
            return {"decoded": {}, "evaluation": {"results": []}}
        wh = raw.get("warehouseCode", "") or "UC"
        return {"decoded": {
                    "clientId": "a1", "clientName": brand, "channel": "WHOLESALE",
                    "accountCode": "MACYS", "warehouseCode": wh,
                    "warehouseInfo": ({"region": "US", "rfid_default": True,
                                       "msrp_required_default": True}
                                      if wh == "UC" else {}),
                    "warnings": []},
                "evaluation": {"results": self._results()}}

    def _results(self):
        return [
            {"domain": "carton", "subtype": "carton_marking", "status": "confirmed",
             "resultJson": {"value": "CTN# + net wt"}},
            dict(self._RED),
            {"domain": "packaging", "subtype": "prepack", "status": "confirmed",
             "resultJson": {"ratio": "1-2-2-1"}},
            {"domain": "hangtag", "status": "confirmed",
             "resultJson": {"pre_pack": "6 pcs/carton"}},
        ]

    def manual_image(self, image_id):
        return None


def _prepack_rows():
    r = _rows()
    for row in r:
        row.is_prepack = True
    return r


def test_export_non_prepack_columns():
    """Non-prepack: EVERY CPRS value shows verbatim — no local gate. Red sticker
    is whatever CPRS confirms (not the old app-forced 无需), and 预包比例 /
    每箱件数 render straight from CPRS regardless of the PO's prepack flag."""
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _rows(), cprs=_MockCprs()))
    last10 = _grid(ws)[9][-10:]  # total, ex_fty, red, mark, packing, prepack, ratio, pcs, msrp, rfid
    assert last10[2] == "MY"            # CPRS-confirmed red sticker code (not 无需)
    assert last10[3] == "CTN# + net wt"  # carton mark
    assert last10[6] == "1-2-2-1"       # 预包比例 from CPRS — no prepack gate
    assert last10[7] == "6"             # 每箱件数 from CPRS regardless of prepack
    assert last10[8] == "Y"             # MSRP (warehouse UC = yes)
    assert last10[9] == "Y"             # RFID


def test_prepack_shows_ratio_and_pcs_box():
    """Prepack: ratio from the CPRS prepack result + pcs mined from wording."""
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _prepack_rows(), cprs=_MockCprs(), manual={"dim_code": "MY"}))
    last10 = _grid(ws)[9][-10:]
    assert last10[2] == "MY"        # red sticker code
    assert last10[6] == "1-2-2-1"   # prepack ratio (from CPRS result)
    assert last10[7] == "6"         # PCs/box from "6 pcs/carton"


def test_non_prepack_red_sticker_follows_cprs_status():
    """Not the old forced 无需 — a non-prepack PO reflects CPRS's actual status."""
    class C(_MockCprs):
        def _results(self):
            return [{"domain": "carton", "subtype": "red_carton_sticker",
                     "status": "pending_input",
                     "resultJson": {"waiting_for": "dim_code"}}]
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _rows(), cprs=C()))   # _rows() is non-prepack
    assert _grid(ws)[9][-10:][2] == "待定:dim_code"


def test_prepack_red_sticker_pending_without_dim_code():
    class C(_MockCprs):
        def _results(self):
            return [{"domain": "carton", "subtype": "red_carton_sticker",
                     "status": "pending_input",
                     "resultJson": {"waiting_for": "dim_code"}}]
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _prepack_rows(), cprs=C()))
    assert _grid(ws)[9][-10:][2] == "待定:dim_code"


def test_prepack_red_sticker_shows_dim_code_when_supplied():
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _prepack_rows(), cprs=_MockCprs(), manual={"dim_code": "MY"}))
    assert _grid(ws)[9][-10:][2] == "MY"   # prepack + supplied DIM code


def test_manual_pcs_box_override():
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _prepack_rows(), cprs=_MockCprs(), manual={"pcs_box": "48"}))
    assert _grid(ws)[9][-10:][7] == "48"   # manual pcs/box wins over CPRS's 36


_TINY_PNG = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00'
             b'\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9c'
             b'c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84\x00\x00\x00\x00'
             b'IEND\xaeB`\x82')


def test_requirement_artwork_embedded_into_cells():
    from po_extractor.ui_helpers.giii_requirements import RowRequirements
    rows = _prepack_rows()
    reqs = {id(r): RowRequirements(red_sticker="MY", red_img=_TINY_PNG,
                                   mark_img=_TINY_PNG) for r in rows}
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               rows, requirements=reqs))
    # one red-sticker + one carton-mark image per row
    assert len(ws._images) == 2 * len(rows)
    # text value still present underneath the artwork
    assert _grid(ws)[9][-10:][2] == "MY"


def test_bad_image_bytes_never_break_export():
    from po_extractor.ui_helpers.giii_requirements import RowRequirements
    rows = _rows()
    reqs = {id(r): RowRequirements(red_img=b"not a png") for r in rows}
    ws = _load(export_giii_buyplan(BuyPlanHeader(), rows, requirements=reqs))
    assert len(ws._images) == 0            # skipped, not crashed


def test_translate_applied_to_carton_mark():
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _rows(), cprs=_MockCprs(), translate=lambda s: "【译】" + s))
    assert _grid(ws)[9][-10:][3] == "【译】CTN# + net wt"


def test_assemble_rows_from_frames():
    import pandas as pd
    from po_extractor.exporters.giii_buyplan_export import assemble_buyplan_rows

    df_size = pd.DataFrame([
        {"po_number": "PO1", "style": "ST1", "color": "NAVY", "size": "S", "units": 10},
        {"po_number": "PO1", "style": "ST1", "color": "NAVY", "size": "M", "units": 20},
        {"po_number": "PO1", "style": "ST1", "color": "CLAY", "size": "S", "units": 5},
    ])
    df_meta = pd.DataFrame([
        {"po_number": "PO1", "style": "ST1", "cpo": "C9", "buyer": "MY MACY'S",
         "ship_to": "NJ DC", "xport_date": "2026-07-01", "packaging": "PPK flat pack"},
    ])
    rows = assemble_buyplan_rows(
        df_size, df_meta,
        contract_by_po={"PO1": "HHN-001"},
        color_lookup={"NAVY": "藏青", "CLAY": "泥粉"},
    )
    assert len(rows) == 2                       # NAVY + CLAY
    navy = next(r for r in rows if r.color_en == "NAVY")
    assert navy.contract_no == "HHN-001"
    assert navy.color_cn == "藏青"
    assert navy.sizes == {"S": 10, "M": 20}
    assert navy.cpo == "C9" and navy.buyer == "MY MACY'S"
    assert navy.ex_fty == "2026-07-01"
    assert navy.is_prepack is True             # "PPK" in packaging


def test_assemble_rows_tolerates_blank_and_decimal_units():
    """A blank (NaN) or decimal-string units cell must not abort the whole buy
    plan — the old int(cell or 0) raised on NaN (truthy) and on '2.0'."""
    import pandas as pd
    from po_extractor.exporters.giii_buyplan_export import assemble_buyplan_rows

    df_size = pd.DataFrame([
        {"po_number": "PO1", "style": "ST1", "color": "NAVY", "size": "S", "units": None},
        {"po_number": "PO1", "style": "ST1", "color": "NAVY", "size": "M", "units": "12.0"},
        {"po_number": "PO1", "style": "ST1", "color": "NAVY", "size": "L", "units": "n/a"},
    ])
    df_meta = pd.DataFrame([{"po_number": "PO1", "style": "ST1"}])
    rows = assemble_buyplan_rows(df_size, df_meta)
    assert len(rows) == 1
    # NaN → 0, "12.0" → 12, "n/a" → 0
    assert rows[0].sizes == {"S": 0, "M": 12, "L": 0}


def test_assemble_rows_empty():
    import pandas as pd
    from po_extractor.exporters.giii_buyplan_export import assemble_buyplan_rows
    assert assemble_buyplan_rows(pd.DataFrame(), pd.DataFrame()) == []


def test_hhn_regex_stops_at_description_text():
    """HHN codes must not swallow trailing CJK description / punctuation — a
    greedy \\S+ captured 'HHN-JA-01715，300克' as one code."""
    from po_extractor.lookups.fabric_lookup import _extract_hhn_numbers
    assert _extract_hhn_numbers("大身：HHN-JA-01715，300克/平方米") == [
        ("大身", "HHN-JA-01715")]
    assert _extract_hhn_numbers("HHN-MS-01794(里布)") == [("", "HHN-MS-01794")]
    # multi-line, hyphenated year-style codes still parse whole
    assert _extract_hhn_numbers("面1 HHN-2026-001\n面2 HHN-DB-YS240782") == [
        ("面1", "HHN-2026-001"), ("面2", "HHN-DB-YS240782")]


def test_fabric_weight_width_tolerate_freetext():
    """Non-numeric weight/width cells ('300g', 'TBC') must not crash the lookup."""
    from po_extractor.lookups.fabric_lookup import _int_or_zero
    assert _int_or_zero("300g") == 300
    assert _int_or_zero("150cm") == 150
    assert _int_or_zero("TBC") == 0
    assert _int_or_zero("") == 0
    assert _int_or_zero(None) == 0
    assert _int_or_zero("48.5") == 48


def test_dynamic_sizes_only_present_ones():
    rows = [BuyPlanRow(style="X", color_en="RED", sizes={"M": 5, "XL": 3})]
    ws = _load(export_giii_buyplan(BuyPlanHeader(), rows, cprs=None))
    grid = _grid(ws)
    sizes_row = grid[8]
    assert "M" in sizes_row and "XL" in sizes_row
    assert "S" not in sizes_row and "L" not in sizes_row
