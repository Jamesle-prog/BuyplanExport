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
    assert wb.sheetnames[0] == "Summary 汇总"
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
    assert len(wb.sheetnames) == 3         # Summary + PO1 + PO1_2
    assert "PO1_2" in wb.sheetnames


def test_export_sanitizes_bad_sheet_names():
    ctx = _ctx("PO/1:*?")
    data = export_giii_requirements([ctx])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    assert len(wb.sheetnames) == 2         # no crash, name sanitized
