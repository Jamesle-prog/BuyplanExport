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
    def resolve_client(self, brand): return "a1" if brand else None
    def resolve_warehouse(self, ship_to, cid): return "UC"
    def resolve_account(self, buyer, cid): return "MACYS"
    def warehouse_flags(self, cid, wh):
        return {"rfid": True, "msrp": True} if wh == "UC" else {"rfid": None, "msrp": None}
    def carton_results(self, order):
        return {
            "red_carton_sticker": {"status": "confirmed",
                                   "resultJson": {"code": "MY"}},
            "carton_marking": {"status": "confirmed",
                               "resultJson": {"value": "CTN# + net wt"}},
        }
    def evaluate(self, order):
        return []
    def prepack_spec(self, cid, account):
        return {"ratio": "1-2-2-1", "pcs_box": "6"}
    def manual_image(self, image_id): return None


def _prepack_rows():
    r = _rows()
    for row in r:
        row.is_prepack = True
    return r


def test_export_non_prepack_columns():
    """Non-prepack: red sticker 无需, and ratio/pcs blank (prepack-only)."""
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _rows(), cprs=_MockCprs()))
    last10 = _grid(ws)[9][-10:]  # total, ex_fty, red, mark, packing, prepack, ratio, pcs, msrp, rfid
    assert last10[2] == "无需"           # non-prepack → red sticker not required
    assert last10[3] == "CTN# + net wt"  # carton mark
    assert last10[6] in ("", None)      # ratio blank (not a prepack)
    assert last10[7] in ("", None)      # pcs/box blank (not a prepack)
    assert last10[8] == "Y"             # MSRP (warehouse UC = yes)
    assert last10[9] == "Y"             # RFID


def test_prepack_shows_ratio_and_pcs_box():
    """Prepack: per-account ratio + pieces-per-bag from prepack_spec."""
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _prepack_rows(), cprs=_MockCprs(), manual={"dim_code": "MY"}))
    last10 = _grid(ws)[9][-10:]
    assert last10[2] == "MY"        # red sticker DIM code
    assert last10[6] == "1-2-2-1"   # prepack ratio (per-account)
    assert last10[7] == "6"         # PCs/box = pieces_per_bag


def test_red_sticker_non_prepack_is_wuxu():
    """Not a prepack → red sticker not required, even if CPRS is pending."""
    class C(_MockCprs):
        def carton_results(self, order):
            return {"red_carton_sticker": {"status": "pending_input",
                    "resultJson": {"waiting_for": "dim_code"}}}
    ws = _load(export_giii_buyplan(BuyPlanHeader(brand="DKNY Sportswear"),
               _rows(), cprs=C()))   # _rows() is non-prepack
    assert _grid(ws)[9][-10:][2] == "无需"


def test_prepack_red_sticker_pending_without_dim_code():
    class C(_MockCprs):
        def carton_results(self, order):
            return {"red_carton_sticker": {"status": "pending_input",
                    "resultJson": {"waiting_for": "dim_code"}}}
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


def test_assemble_rows_empty():
    import pandas as pd
    from po_extractor.exporters.giii_buyplan_export import assemble_buyplan_rows
    assert assemble_buyplan_rows(pd.DataFrame(), pd.DataFrame()) == []


def test_dynamic_sizes_only_present_ones():
    rows = [BuyPlanRow(style="X", color_en="RED", sizes={"M": 5, "XL": 3})]
    ws = _load(export_giii_buyplan(BuyPlanHeader(), rows, cprs=None))
    grid = _grid(ws)
    sizes_row = grid[8]
    assert "M" in sizes_row and "XL" in sizes_row
    assert "S" not in sizes_row and "L" not in sizes_row
