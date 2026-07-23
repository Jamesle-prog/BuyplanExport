"""API requirements document (CPRS /export/requirements-doc ≥1.6.14):
request-builder purity, grouping, and the pass-through-verbatim contract.

The design principle under test: the app INVENTS NOTHING. Missing CPO/MSRP
stay empty (the API renders 待定 itself), fob/amount are always passed (the
variant — an API concern — decides whether they render), and the order
context is exactly the one /evaluate/po gets.
"""
from __future__ import annotations

from po_extractor.models.po_data import POData, POMetadata, SizeRow
from po_extractor.ui_helpers.giii_requirements import (
    build_requirements_api_requests, raw_po_context,
)


def _po(po_number="6503123", style="DU5105", customer="Macy's",
        dest="WRHUS01", ship_to="Carlstadt NJ", coo="CHINA",
        cpo="", msrp="", unit_cost="", rows=None, division="DKNY"):
    m = POMetadata(po_number=po_number, style=style, customer=customer,
                   destination_code=dest, ship_to=ship_to,
                   country_of_origin=coo, cpo=cpo, msrp=msrp,
                   unit_cost=unit_cost, division_name=division,
                   factory_ship_date="2026-09-01")
    return POData(metadata=m, size_rows=rows if rows is not None else [
        SizeRow(po_number=po_number, style=style, color="BLACK", size="S",
                units=10, upc="000000000001"),
        SizeRow(po_number=po_number, style=style, color="BLACK", size="M",
                units=20, upc="000000000002"),
        SizeRow(po_number=po_number, style=style, color="IVORY", size="M",
                units=5, upc="000000000003"),
    ])


# ── raw_po_context ──────────────────────────────────────────────────────────

def test_context_passes_fields_through_verbatim():
    ctx = raw_po_context(_po().metadata, "DKNY")
    assert ctx["brand"] == "DKNY"
    assert ctx["poNumber"] == "6503123"
    assert ctx["warehouseCode"] == "US01"        # WRH prefix stripped
    assert ctx["shipTo"] == "Carlstadt NJ"
    assert ctx["account"] == "Macy's"
    assert ctx["coo"] == "CHINA"


def test_context_omits_account_when_no_customer():
    ctx = raw_po_context(_po(customer="").metadata, "DKNY")
    assert "account" not in ctx                  # CPRS applies brand defaults


# ── build_requirements_api_requests ────────────────────────────────────────

def test_one_document_per_order_context():
    reqs, warns = build_requirements_api_requests(
        [_po(po_number="A1"), _po(po_number="A2"),
         _po(po_number="B1", customer="Ross")])
    assert warns == []
    assert len(reqs) == 2                        # Macy's ctx + Ross ctx
    by_label = {r["label"]: r for r in reqs}
    macys = next(r for lbl, r in by_label.items() if "Macy's" in lbl)
    assert [p["order"] for p in macys["body"]["pos"]] == ["A1", "A2"]


def test_pos_row_shape_and_aggregation():
    reqs, _ = build_requirements_api_requests([_po()])
    row = reqs[0]["body"]["pos"][0]
    assert row["order"] == "6503123"
    assert row["giiiSalesOrder"] == "6503123"
    assert row["style"] == "DU5105"
    assert row["color"] == "BLACK / IVORY"       # distinct, order-preserving
    assert row["qty"] == 35
    assert row["sizes"] == "S×10 M×20 M×5"
    assert row["etd"] == "2026-09-01"


def test_missing_cpo_and_msrp_stay_empty_never_invented():
    reqs, _ = build_requirements_api_requests([_po(cpo="", msrp="")])
    row = reqs[0]["body"]["pos"][0]
    assert row["cpo"] == "" and row["msrp"] == ""   # API renders 待定 itself


def test_business_fields_always_passed_variant_is_api_policy():
    reqs, _ = build_requirements_api_requests(
        [_po(unit_cost="12.50", msrp="$59", cpo="CPO-77")])
    row = reqs[0]["body"]["pos"][0]
    assert row["fob"] == "12.50"
    assert row["msrp"] == "$59"
    assert row["cpo"] == "CPO-77"
    # ...and the app sets no variant here — that's chosen at generation time.
    assert "variant" not in reqs[0]["body"]


def test_group_body_has_no_per_po_style():
    """style differs per PO inside one context, so it must not leak into the
    group-level context (it travels in pos[] instead)."""
    reqs, _ = build_requirements_api_requests(
        [_po(po_number="A1", style="DU1"), _po(po_number="A2", style="DU2")])
    assert "style" not in reqs[0]["body"]
    assert {p["style"] for p in reqs[0]["body"]["pos"]} == {"DU1", "DU2"}


def test_brandless_po_warns_and_is_skipped():
    bad = _po(po_number="ZZZZ", division="")
    reqs, warns = build_requirements_api_requests([bad])
    assert reqs == []
    assert any("ZZZZ" in w for w in warns)


def test_builder_is_pure_no_cprs_needed():
    """The builder must not require a CPRS client at all (runs at upload)."""
    reqs, _ = build_requirements_api_requests([_po()])
    assert reqs and "pos" in reqs[0]["body"]


# ── client method ───────────────────────────────────────────────────────────

def test_export_requirements_doc_none_without_base():
    from po_extractor.utils.cprs_client import CprsClient
    c = CprsClient("")                            # unconfigured
    assert c.export_requirements_doc({"brand": "DKNY"}) is None


def test_export_requirements_doc_returns_html_and_headers(monkeypatch):
    from po_extractor.utils import cprs_client as mod

    class _Resp:
        status_code = 200
        content = b"<html>doc</html>"
        headers = {"X-CPRS-Run-Id": "r1", "X-CPRS-Card-Count": "28",
                   "X-CPRS-Image-Count": "51"}

    class _Requests:
        @staticmethod
        def post(url, json=None, headers=None, timeout=None):
            assert url.endswith("/api/v1/export/requirements-doc")
            assert json["variant"] == "factory"
            return _Resp()

    import sys
    monkeypatch.setitem(sys.modules, "requests", _Requests)
    c = mod.CprsClient("http://localhost:3100")
    out = c.export_requirements_doc({"brand": "DKNY", "variant": "factory"})
    assert out["html"] == b"<html>doc</html>"
    assert (out["run_id"], out["card_count"], out["image_count"]) == \
        ("r1", "28", "51")
