"""Tests for the upload-time PO requirements document (resolver + Excel)."""
from __future__ import annotations

import io

import openpyxl

from po_extractor.models.po_data import POData, POMetadata
from po_extractor.exporters.giii_requirements_export import export_giii_requirements
from po_extractor.ui_helpers.giii_requirements import resolve_po_requirements


class _Cprs:
    def __init__(self):
        self.eval_calls = 0

    def resolve_client(self, brand):
        return "a1" if "DKNY" in (brand or "").upper() else None
    def list_accounts(self, cid):
        return [{"account_code": "MACYS", "account_type": "WHOLESALE"}]
    def resolve_account(self, buyer, cid):
        return "MACYS" if "MACY" in (buyer or "").upper() else None
    def resolve_warehouse(self, ship_to, cid):
        return "UC" if ship_to else None
    def evaluate(self, order):
        self.eval_calls += 1
        return [
            {"domain": "label", "subtype": "care_label", "status": "confirmed",
             "resultJson": {"standard": "Care label per FTC", "source": "Manual p3"}},
            {"domain": "carton", "subtype": "red_carton_sticker",
             "status": "pending_input", "resultJson": {"waiting_for": "dim_code"}},
            {"domain": "packaging", "subtype": "polybag", "status": "not_applicable",
             "resultJson": {}},
        ]


def _po(po="PO1", division="DKNY Sportswear", dest="UC", buyer="MY MACY'S"):
    return POData(metadata=POMetadata(po_number=po, style="ST1",
                                      division_name=division,
                                      destination_code=dest, buyer=buyer,
                                      country_of_origin="China"))


# ── resolver ─────────────────────────────────────────────────────────────────

def test_resolver_builds_contexts_and_dedups():
    cprs = _Cprs()
    contexts, warns = resolve_po_requirements(cprs, [_po("PO1"), _po("PO2")])
    assert len(contexts) == 2
    assert cprs.eval_calls == 1            # same order context → one evaluation
    assert contexts[0]["warehouse"] == "UC"    # from destination_code directly
    assert contexts[0]["account"] == "MACYS"
    assert warns == []


def test_resolver_unknown_brand_warns_and_skips():
    contexts, warns = resolve_po_requirements(_Cprs(), [_po(division="ACME")])
    assert contexts == []
    assert any("not found in CPRS" in w for w in warns)


def test_resolver_no_cprs():
    contexts, warns = resolve_po_requirements(None, [_po()])
    assert contexts == [] and any("not configured" in w for w in warns)


# ── exporter ─────────────────────────────────────────────────────────────────

def _ctx(po="PO1"):
    return {"po_number": po, "style": "ST1", "brand": "DKNY Sportswear",
            "warehouse": "UC", "account": "MACYS", "channel": "WHOLESALE",
            "results": _Cprs().evaluate({})}


def test_export_summary_and_per_po_sheets():
    data = export_giii_requirements([_ctx("PO1"), _ctx("PO2")],
                                    warnings=["something to know"])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames[0] == "PO Index"          # KL layout leads with PO Index
    assert "Summary 汇总" in wb.sheetnames
    assert "PO1" in wb.sheetnames and "PO2" in wb.sheetnames

    ws = wb["Summary 汇总"]
    # header + one row per PO; counts: 1 confirmed, 1 pending, 0 conflict, 1 N/A
    assert ws.cell(2, 1).value == "PO1"
    assert ws.cell(2, 7).value == 1 and ws.cell(2, 8).value == 1
    assert ws.cell(2, 10).value == 1
    flat = [c.value for row in ws.iter_rows() for c in row]
    assert "something to know" in flat

    s = wb["PO1"]
    rows = [[c.value for c in row] for row in s.iter_rows()]
    flat = [c for r in rows for c in r]
    assert "care_label" in flat
    assert any(v and "待定" in str(v) for v in flat)      # pending marker
    assert "Care label per FTC" in " ".join(str(v) for v in flat if v)
    # N/A rows sort last: last data row is the polybag one
    assert "polybag" in [str(v) for v in rows[-1]]


def test_missing_mandatory_context_counts_as_pending():
    """A PO whose results all need context must not show 0/0/0/0 in Summary."""
    ctx = {"po_number": "PO9", "style": "S", "brand": "B", "warehouse": "",
           "account": "", "channel": "WHOLESALE",
           "results": [{"domain": "label", "subtype": "x",
                        "status": "missing_mandatory_context", "resultJson": {}}]}
    wb = openpyxl.load_workbook(io.BytesIO(export_giii_requirements([ctx])))
    ws = wb["Summary 汇总"]
    assert ws.cell(2, 8).value == 1        # folded into 待定 Pending
    flat = [c.value for row in wb["PO9"].iter_rows() for c in row]
    assert any(v and "缺少信息" in str(v) for v in flat)


def test_export_duplicate_po_numbers_get_unique_sheets():
    data = export_giii_requirements([_ctx("PO1"), _ctx("PO1")])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert "PO1" in wb.sheetnames and "PO1_2" in wb.sheetnames     # unique per-PO


def test_export_sanitizes_bad_sheet_names():
    ctx = _ctx("PO/1:*?")
    data = export_giii_requirements([ctx])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    # no crash; the fixed KL-style sheets are present alongside the sanitized PO
    assert "PO Index" in wb.sheetnames and "Requirement Matrix" in wb.sheetnames


# ── KL-style illustrated sheets ───────────────────────────────────────────────

def _ctx_kl(po, style, account, region, units, results):
    return {"po_number": po, "style": style, "brand": "Karl Lagerfeld",
            "warehouse": "NJ", "account": account, "channel": "WHOLESALE",
            "units": units, "article": "KL-9727", "region": region,
            "destination": "US — Dayton, NJ", "packing": "Flat pack", "msrp": "59",
            "coo": "China", "source_file": f"{po}.pdf", "is_prepack": False,
            "results": results}


def test_full_kl_layout_sheet_order():
    r = [{"domain": "label", "subtype": "main_label", "status": "confirmed",
          "resultJson": {"standard": "Main label", "source": "KL Manual"}}]
    data = export_giii_requirements([_ctx_kl("P1", "ST1", "", "US", 80, r)])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert wb.sheetnames[:7] == [
        "PO Index", "Summary 汇总", "款号对比 By Style", "Requirements + Pictures",
        "Requirement Matrix", "Pre-pack", "Actions & Confirm"]


def test_po_index_sheet_lists_pos_and_total():
    r = [{"domain": "label", "subtype": "x", "status": "confirmed", "resultJson": {}}]
    data = export_giii_requirements([
        _ctx_kl("P1", "ST1", "", "US", 80, r),
        _ctx_kl("P2", "ST1", "AMRG", "US", 3740, r)])
    ws = openpyxl.load_workbook(io.BytesIO(data))["PO Index"]
    hdr = [ws.cell(2, c).value for c in range(1, 11)]
    assert hdr[:4] == ["PO Number", "款号 Style", "品名 Article", "数量 Units"]
    vals = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    assert "P1" in vals and "P2" in vals and "3740" in vals
    assert "TOTAL" in vals and "3820" in vals            # 80 + 3740


def test_requirement_matrix_columns_by_destination():
    common = {"domain": "label", "subtype": "main_label", "status": "confirmed",
              "resultJson": {"standard": "Main label"}}
    only_amrg = {"domain": "carton", "subtype": "red_sticker",
                 "status": "confirmed", "resultJson": {}}
    data = export_giii_requirements([
        _ctx_kl("P1", "ST1", "", "US", 80, [dict(common)]),
        _ctx_kl("P2", "ST1", "AMRG", "US", 100, [dict(common), dict(only_amrg)])])
    ws = openpyxl.load_workbook(io.BytesIO(data))["Requirement Matrix"]
    hdr = [ws.cell(2, c).value for c in range(1, ws.max_column + 1)]
    assert hdr[0] == "Domain / Subtype" and "STOCK (US)" in hdr and "AMRG (US)" in hdr
    rows = [[c.value for c in row] for row in ws.iter_rows(min_row=3)]
    red = next(r for r in rows if r[0] == "carton/red_sticker")
    si, ai = hdr.index("STOCK (US)"), hdr.index("AMRG (US)")
    assert red[ai] == "✓" and red[si] == "—"       # only AMRG has the red sticker


def test_actions_sheet_flags_conflicts():
    r = [{"domain": "hangtag", "subtype": "main_hangtag", "status": "conflict",
          "resultJson": {"standard": "two rules disagree"}}]
    data = export_giii_requirements([_ctx_kl("P1", "ST1", "", "US", 80, r)])
    ws = openpyxl.load_workbook(io.BytesIO(data))["Actions & Confirm"]
    vals = [str(c.value) for row in ws.iter_rows() for c in row if c.value is not None]
    assert any("Conflict" in v for v in vals) and "Confirm" in vals


# ── by-style comparison sheet ─────────────────────────────────────────────────

def _ctx_style(po, style, results):
    return {"po_number": po, "style": style, "brand": "DKNY Sportswear",
            "warehouse": "UC", "account": "MACYS", "channel": "WHOLESALE",
            "results": results}


def test_by_style_sheet_combines_shared_and_splits_differing():
    shared = {"domain": "label", "subtype": "care_label", "status": "confirmed",
              "resultJson": {"standard": "Care label per FTC"}}
    reqA = {"domain": "carton", "subtype": "carton_mark", "status": "confirmed",
            "resultJson": {"standard": "Mark ABC"}}
    reqB = {"domain": "carton", "subtype": "carton_mark", "status": "confirmed",
            "resultJson": {"standard": "Mark XYZ"}}
    data = export_giii_requirements([
        _ctx_style("PO1", "STYLE_A", [dict(shared), dict(reqA)]),
        _ctx_style("PO2", "STYLE_B", [dict(shared), dict(reqB)]),
    ])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert "款号对比 By Style" in wb.sheetnames
    s = wb["款号对比 By Style"]
    rows = [[c.value for c in row] for row in s.iter_rows(min_row=3)]
    # care_label is identical across both styles → one row, "全部 All (2)"
    care = [r for r in rows if r[1] == "care_label"]
    assert len(care) == 1 and "全部 All (2)" in str(care[0][4])
    # carton_mark differs → two rows, each scoped to its own style
    marks = [r for r in rows if r[1] == "carton_mark"]
    assert len(marks) == 2
    style_cells = {str(r[4]) for r in marks}
    assert style_cells == {"STYLE_A", "STYLE_B"}
    assert any("Mark ABC" in str(r[3]) for r in marks)
    assert any("Mark XYZ" in str(r[3]) for r in marks)


# ── images ────────────────────────────────────────────────────────────────────

def _png(color="red") -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (30, 20), color).save(b, format="PNG")
    return b.getvalue()


def test_all_pictures_embedded_on_po_sheet():
    res = {"domain": "carton", "subtype": "red_carton_sticker", "status": "confirmed",
           "resultJson": {}, "_images": [_png("red"), _png("blue")]}
    ctx = _ctx_style("PO1", "ST1", [res])
    wb = openpyxl.load_workbook(io.BytesIO(export_giii_requirements([ctx])))
    s = wb["PO1"]
    assert s.cell(2, 6).value == "图示 Image"        # image column header
    assert len(s._images) == 2                       # BOTH pictures embedded


def test_bad_image_bytes_do_not_break_export():
    res = {"domain": "carton", "subtype": "x", "status": "confirmed",
           "resultJson": {}, "_images": [b"not-a-png"]}
    wb = openpyxl.load_workbook(io.BytesIO(
        export_giii_requirements([_ctx_style("PO1", "ST1", [res])])))
    assert wb["PO1"]._images == []                   # skipped, no crash


# ── resolver attaches all image bytes ─────────────────────────────────────────

class _CprsImg(_Cprs):
    def __init__(self):
        super().__init__()
        self.fetches = []

    def evaluate(self, order):
        self.eval_calls += 1
        return [
            {"domain": "carton", "subtype": "red_carton_sticker",
             "status": "confirmed", "resultJson": {},
             "images": [{"id": "img-1"}, {"id": "img-2"}]},
        ]

    def manual_image(self, image_id):
        self.fetches.append(image_id)
        return f"BYTES:{image_id}".encode()


def test_resolver_attaches_all_image_bytes_deduped():
    cprs = _CprsImg()
    contexts, _ = resolve_po_requirements(cprs, [_po("PO1"), _po("PO2")])
    imgs = contexts[0]["results"][0]["_images"]
    assert imgs == [b"BYTES:img-1", b"BYTES:img-2"]   # ALL images fetched
    # two POs share one order context → each image fetched once, not per-PO
    assert sorted(cprs.fetches) == ["img-1", "img-2"]
