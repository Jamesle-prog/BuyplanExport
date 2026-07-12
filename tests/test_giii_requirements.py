"""Tests for the GIII requirements-resolution service (CPRS integration layer)."""
from __future__ import annotations

from po_extractor.exporters.giii_buyplan_export import BuyPlanRow
from po_extractor.ui_helpers.giii_requirements import (
    RowRequirements, _channel_for, resolve_requirements,
)


class _Cprs:
    def __init__(self):
        self.evaluate_calls = 0
        self.wh_calls = 0

    def resolve_client(self, brand): return "a1" if brand else None
    def list_accounts(self, cid):
        return [{"account_code": "MACYS_COM", "account_type": "E_COMMERCE"},
                {"account_code": "ROSS", "account_type": "OFF_PRICE"}]
    def resolve_account(self, buyer, cid):
        up = (buyer or "").upper()
        if "MACY" in up: return "MACYS_COM"
        if "ROSS" in up: return "ROSS"
        return None
    def resolve_warehouse(self, ship_to, cid):
        self.wh_calls += 1
        return "UC" if ship_to else None
    def list_warehouses(self, cid):
        return [{"warehouse_code": "UC"}, {"warehouse_code": "DN"}]
    def warehouse_flags(self, cid, wh):
        return {"rfid": True, "msrp": True} if wh == "UC" else {"rfid": None, "msrp": None}
    def carton_results(self, order):
        self.evaluate_calls += 1
        return {"carton_marking": {"status": "confirmed",
                                   "resultJson": {"value": "CTN#"}}}
    def evaluate(self, order): return []
    def prepack_spec(self, cid, account):
        return {"ratio": "4-14 1-1", "pcs_box": "6"} if account == "ROSS" else {"ratio": "", "pcs_box": ""}
    def manual_image(self, image_id): return None


def _row(**over):
    base = dict(style="ST", po_number="PO1", warehouse_code="UC",
                buyer="MY MACY'S", color_en="NAVY", sizes={"S": 1})
    base.update(over)
    return BuyPlanRow(**base)


def test_channel_derived_from_account_type():
    assert _channel_for("E_COMMERCE") == "ECOMM"
    assert _channel_for("ECOMM") == "ECOMM"
    assert _channel_for("OFF_PRICE") == "OFF_PRICE"
    assert _channel_for("RETAIL") == "RETAIL"
    assert _channel_for("") == "WHOLESALE"


def test_resolution_and_channel():
    reqs, warns = resolve_requirements(_Cprs(), "DKNY", [_row()])
    q = list(reqs.values())[0]
    assert isinstance(q, RowRequirements)
    assert q.channel == "ECOMM"           # MACYS_COM is E_COMMERCE, not WHOLESALE
    assert q.msrp == "Y" and q.rfid == "Y"
    assert q.carton_mark == "CTN#"
    assert warns == []


def test_context_dedup_resolves_once_for_same_context():
    cprs = _Cprs()
    rows = [_row(color_en="NAVY"), _row(color_en="CLAY"), _row(color_en="RED")]
    reqs, _ = resolve_requirements(cprs, "DKNY", rows)
    assert len(reqs) == 3                  # every row got requirements
    assert cprs.evaluate_calls == 1        # ...from ONE resolution (same context)


def test_unmatched_buyer_warns_not_silently_blank():
    reqs, warns = resolve_requirements(_Cprs(), "DKNY", [_row(buyer="MYSTERY SHOP")])
    assert any("didn't match a CPRS account" in w for w in warns)
    assert list(reqs.values())[0].account == ""


def test_no_cprs_and_no_brand_warn():
    _, w1 = resolve_requirements(None, "DKNY", [_row()])
    assert any("not configured" in w for w in w1)
    _, w2 = resolve_requirements(_Cprs(), "", [_row()])
    assert any("No brand" in w for w in w2)


def test_warehouse_from_po_suffix_when_no_code_or_ship_to():
    """DKNY POs carry the DC code as the PO-number suffix (DW843120DN → DN);
    only trusted when it is one of the client's real warehouse codes."""
    cprs = _Cprs()
    rows = [_row(po_number="DW843120DN", warehouse_code="", ship_to=""),
            _row(po_number="DW843124UC", warehouse_code="", ship_to="", color_en="X"),
            _row(po_number="LKHHN0045", warehouse_code="", ship_to="", color_en="Y")]
    reqs, _ = resolve_requirements(cprs, "DKNY", rows)
    assert reqs[id(rows[0])].warehouse == "DN"
    assert reqs[id(rows[1])].warehouse == "UC"
    assert reqs[id(rows[2])].warehouse == ""      # "45" is not a DC code
    assert cprs.wh_calls == 0                     # no ship-to lookups needed


class _CprsEvidence(_Cprs):
    """No brand resolves; only client a1 matches the buyer/ship-to evidence."""
    def resolve_client(self, brand): return None
    def list_clients(self):
        return [{"id": "a1", "name": "DKNY Sportswear"},
                {"id": "c3", "name": "Karl Lagerfeld Suits"}]
    def list_warehouses(self, cid):
        return super().list_warehouses(cid) if cid == "a1" else []
    def resolve_account(self, buyer, cid):
        return super().resolve_account(buyer, cid) if cid == "a1" else None
    def resolve_warehouse(self, ship_to, cid):
        return "DW" if (cid == "a1" and ship_to) else None


def test_evidence_fallback_picks_client_for_brandless_fax_pos():
    rows = [_row(po_number="CSKHHN015R", warehouse_code="",
                 buyer="ROSS STORES", ship_to="ROSS STORES PERRIS CA",
                 is_prepack=True)]
    reqs, warns = resolve_requirements(_CprsEvidence(), "6106.20.2010", rows)
    assert any("evidence" in w for w in warns)
    q = reqs[id(rows[0])]
    assert q.warehouse == "DW"                    # ship-to ZIP match (Ross POE)
    assert q.account == "ROSS"
    assert q.channel == "OFF_PRICE"


def test_evidence_ambiguity_warns_instead_of_guessing():
    class _Ambiguous(_CprsEvidence):
        def resolve_account(self, buyer, cid):
            return "ROSS"                          # every client matches
        def list_warehouses(self, cid): return []
        def resolve_warehouse(self, ship_to, cid): return None
    reqs, warns = resolve_requirements(_Ambiguous(), "", [_row(buyer="ROSS")])
    assert reqs == {}
    assert any("ambiguous" in w for w in warns)
    # the tied candidates are named so the operator knows what to pick
    assert any("DKNY Sportswear" in w and "Karl Lagerfeld" in w for w in warns)


def test_per_po_dim_codes_override_global():
    rows = [_row(po_number="PO1", buyer="ROSS", is_prepack=True),
            _row(po_number="PO2", buyer="ROSS", is_prepack=True, color_en="X")]
    reqs, _ = resolve_requirements(
        _Cprs(), "DKNY", rows,
        manual={"dim_code": "GL", "dim_codes": {"PO1": "AA"}})
    assert reqs[id(rows[0])].red_sticker == "AA"   # per-PO override
    assert reqs[id(rows[1])].red_sticker == "GL"   # global fallback


def test_prepack_rows_get_ratio_and_warn_when_missing():
    rows = [_row(buyer="ROSS", is_prepack=True),
            _row(buyer="MY MACY'S", is_prepack=True, color_en="X")]
    reqs, warns = resolve_requirements(_Cprs(), "DKNY", rows,
                                       manual={"dim_code": "RO"})
    ross = reqs[id(rows[0])]
    assert ross.prepack_ratio == "4-14 1-1" and ross.pcs_box == "6"
    assert ross.red_sticker == "RO"
    # MACYS_COM has no ratio on file → warned, not silent
    assert any("no prepack ratio" in w for w in warns)
