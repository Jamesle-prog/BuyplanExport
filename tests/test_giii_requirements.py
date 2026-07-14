"""Tests for the GIII requirements-resolution service (CPRS integration layer)."""
from __future__ import annotations

from po_extractor.exporters.giii_buyplan_export import BuyPlanRow
from po_extractor.ui_helpers.giii_requirements import (
    RowRequirements, _channel_for, brand_from_po, brand_of, resolve_requirements,
)


def test_brand_of_prefers_canonical_over_raw_division():
    """The parser stores a raw division code ("DW") or abbreviation
    ("DKNY W/SPRTSWR") that CPRS 400s on — brand_of maps it to the canonical
    name via the PO prefix, falling back to the division text when unknown."""
    assert brand_of("DWCCC013DS", "DW") == "DKNY Sportswear"
    assert brand_of("DWCCC013DS", "DKNY W/SPRTSWR") == "DKNY Sportswear"
    assert brand_of("CS123456", "CS") == "Calvin Klein"
    assert brand_of("LS123456", "LS") == "Karl Lagerfeld"
    # Unknown prefix → fall back to the division text (best effort)
    assert brand_of("XX999999", "Some Brand") == "Some Brand"
    assert brand_of("", "") == ""


def test_clean_warehouse_strips_wrh_prefix():
    from po_extractor.ui_helpers.giii_requirements import clean_warehouse
    # The parser stores 'WRHUC'; CPRS wants the bare 'UC'
    assert clean_warehouse("WRHUC") == "UC"
    assert clean_warehouse("WRHDS") == "DS"
    assert clean_warehouse("UC") == "UC"        # already clean — unchanged
    assert clean_warehouse("WRH") == "WRH"      # too short to be prefix+code
    assert clean_warehouse("") == ""
    assert clean_warehouse(None) == ""


def test_pcs_per_carton_mined_from_requirement_wording():
    """CK states the pack-out inside the hangtag requirement ('6 pre-packs
    per box, 36 pcs/carton') — 每箱件数 reads it from the evaluate results."""
    from po_extractor.ui_helpers.giii_requirements import _pcs_from_results

    results = [
        {"domain": "hangtag", "subtype": "main_hangtag", "status": "confirmed",
         "resultJson": {"pre_pack": {"blouses_camis":
             "Follow ratio on PO, 6 pre-packs per box, 36 pcs/carton"}}},
    ]
    assert _pcs_from_results(results) == "36"
    # category-mixed wording: EVERY distinct figure is surfaced, not just the
    # first clause (blouses 36 vs jackets 12 — context can't tell which)
    mixed = [{"domain": "hangtag", "status": "confirmed", "resultJson": {
        "pre_pack": {"blouses_camis": "6 pre-packs per box, 36 pcs/carton",
                     "jackets_pants_skirts": "2 pre-packs per box, 12 pcs/carton"}}}]
    assert _pcs_from_results(mixed) == "36/12"
    # structured key wins; non-confirmed and other domains are ignored
    assert _pcs_from_results([{"domain": "packaging", "status": "confirmed",
                               "resultJson": {"pieces_per_carton": 24}}]) == "24"
    assert _pcs_from_results([{"domain": "hangtag", "status": "pending_input",
                               "resultJson": {"x": "36 pcs/carton"}}]) == ""
    assert _pcs_from_results([{"domain": "label", "status": "confirmed",
                               "resultJson": {"x": "36 pcs/carton"}}]) == ""
    assert _pcs_from_results([]) == ""


def test_carton_weight_limit_explicit_bounds():
    from po_extractor.ui_helpers.giii_requirements import _weight_from_results

    # Upper-only rules render an explicit 上限 — and say nothing about a lower
    corporate = [{"domain": "carton", "subtype": "carton_spec", "status": "confirmed",
                  "resultJson": {"max_weight": "40 lbs / 18 kg per carton"}}]
    kl = [{"domain": "carton", "subtype": "carton_spec", "status": "confirmed",
           "resultJson": {"max_weight_lbs": 40}}]
    # Numeric values always show the equivalent in the other unit; the
    # corporate free-text already carries both units and passes through.
    assert _weight_from_results(corporate) == "上限 40 lbs / 18 kg per carton"
    assert _weight_from_results(kl) == "上限 40 lbs (18.1 kg)"

    # kg-stated limits get the lbs equivalent (KL TJX Australia)
    au = [{"domain": "carton", "subtype": "carton_spec", "status": "confirmed",
           "resultJson": {"max_carton_weight_kg": 22.68}}]
    assert _weight_from_results(au) == "上限 22.68 kg (50 lbs)"

    # A stated range ("weight_lbs": "5-40") makes BOTH bounds explicit
    ck_range = [{"domain": "carton", "subtype": "carton_marking",
                 "status": "confirmed",
                 "resultJson": {"carton": {"weight_lbs": "5-40"}}}]
    assert _weight_from_results(ck_range) == "下限 5 lbs (2.3 kg) / 上限 40 lbs (18.1 kg)"

    # Corporate max + brand range combine: range supplies the missing lower
    combined = corporate + ck_range
    assert _weight_from_results(combined) == \
        "下限 5 lbs (2.3 kg) / 上限 40 lbs / 18 kg per carton"

    # carton_marking's net/gross weight are MARKING fields, not limits;
    # pallet_spec maxes are pallet limits, not carton limits
    marking_only = [{"domain": "carton", "subtype": "carton_marking",
                     "status": "confirmed",
                     "resultJson": {"net_weight": "YES - printed on carton",
                                    "gross_weight": "YES - printed"}}]
    pallet = [{"domain": "carton", "subtype": "pallet_spec", "status": "confirmed",
               "resultJson": {"max_weight_lb": 2200}}]
    assert _weight_from_results(marking_only) == ""
    assert _weight_from_results(pallet) == ""
    assert _weight_from_results([]) == ""

    # a value that already carries its unit is not double-suffixed
    from po_extractor.ui_helpers.giii_requirements import _fmt_weight
    assert _fmt_weight("40 lbs", "lbs") == "40 lbs"
    assert _fmt_weight("40-ish", "kg") == "40-ish kg"


def test_image_bytes_prefers_v165_images_array():
    """CPRS ≥1.6.5 attaches artwork as images[] on each result; the old
    resultJson.image_id shape must still work as the fallback."""
    from po_extractor.ui_helpers.giii_requirements import _image_bytes

    class _C:
        def manual_image(self, image_id):
            return f"bytes:{image_id}".encode()

    new_shape = {"status": "confirmed",
                 "images": [{"id": "IMG_NEW", "caption": "red sticker",
                             "url": "/api/v1/manual-images/IMG_NEW/file"}],
                 "resultJson": {"image_id": "IMG_OLD"}}
    old_shape = {"status": "confirmed", "resultJson": {"image_id": "IMG_OLD"}}
    assert _image_bytes(_C(), new_shape) == b"bytes:IMG_NEW"
    assert _image_bytes(_C(), old_shape) == b"bytes:IMG_OLD"
    assert _image_bytes(_C(), {"status": "confirmed", "resultJson": {}}) is None
    assert _image_bytes(_C(), None) is None


def test_brand_from_po_prefix_decode():
    """Documented GIII division prefixes decode; anything else stays ''."""
    assert brand_from_po("CSKHHN015R") == "Calvin Klein"
    assert brand_from_po("LSKHHN008R") == "Karl Lagerfeld"
    assert brand_from_po("DW843124UC") == "DKNY Sportswear"
    assert brand_from_po("dwhhn000dn") == "DKNY Sportswear"   # case-insensitive
    assert brand_from_po("DUKHHA057R") == ""    # DU not documented → no guess
    assert brand_from_po("12345678") == ""      # digits → not a division code
    assert brand_from_po("PO1") == ""            # too short
    assert brand_from_po("") == ""


class _Cprs:
    """Fake CPRS whose /evaluate/po decodes a raw PO and evaluates it — mirrors
    the live ``{decoded, evaluation}`` shape. The app no longer resolves client/
    warehouse/account/channel itself; CPRS's ``decoded`` block does."""
    def __init__(self):
        self.calls = 0

    def evaluate_po(self, raw):
        self.calls += 1
        brand = str(raw.get("brand", "")).strip()
        if not brand or "UNKNOWN" in brand.upper():
            return {"decoded": {}, "evaluation": {"results": []}}
        acct_txt = str(raw.get("account", "")).upper()
        acct = ("MACYS_COM" if "MACY" in acct_txt
                else "ROSS" if "ROSS" in acct_txt else "")
        wh = raw.get("warehouseCode", "")
        whinfo = ({"region": "US", "rfid_default": True,
                   "msrp_required_default": True} if wh == "UC" else {})
        dim = (raw.get("contextFields") or {}).get("dim_code", "")
        red = {"domain": "carton", "subtype": "red_carton_sticker",
               "status": "pending_input" if dim else "confirmed",
               "resultJson": ({"waiting_for": "dim_code"} if dim else {}),
               "images": [{"id": "IMG_RED"}]}
        results = [
            {"domain": "carton", "subtype": "carton_marking", "status": "confirmed",
             "resultJson": {"value": "CTN#"}},
            {"domain": "carton", "subtype": "carton_spec", "status": "confirmed",
             "resultJson": {"max_weight": "40 lbs / 18 kg per carton"}},
            {"domain": "hangtag", "status": "confirmed",
             "resultJson": {"pre_pack": "6 pre-packs per box, 36 pcs/carton"}},
            red,
        ]
        return {"decoded": {"clientId": "a1", "clientName": brand,
                            "channel": "RETAIL" if acct else "WHOLESALE",
                            "accountCode": acct, "warehouseCode": wh,
                            "warehouseInfo": whinfo, "warnings": []},
                "evaluation": {"results": results}}

    def manual_image(self, image_id):
        return f"bytes:{image_id}".encode()


def _row(**over):
    base = dict(style="ST", po_number="PO1", warehouse_code="UC",
                buyer="MY MACY'S", color_en="NAVY", sizes={"S": 1})
    base.update(over)
    return BuyPlanRow(**base)


def test_channel_derived_helper_still_available():
    # _channel_for is no longer used by the resolver (CPRS decodes channel), but
    # the pure helper stays valid.
    assert _channel_for("E_COMMERCE") == "ECOMM"
    assert _channel_for("") == "WHOLESALE"


def test_values_come_straight_from_evaluate_po():
    reqs, warns = resolve_requirements(_Cprs(), "DKNY", [_row(warehouse_code="UC")])
    q = list(reqs.values())[0]
    assert isinstance(q, RowRequirements)
    assert q.channel == "RETAIL"             # CPRS decoded the account → channel
    assert q.account == "MACYS_COM"
    assert q.warehouse == "UC" and q.region == "US"
    assert q.msrp == "Y" and q.rfid == "Y"    # from decoded.warehouseInfo
    assert q.carton_mark == "CTN#"
    assert q.carton_weight == "上限 40 lbs / 18 kg per carton"
    assert q.pcs_box == "36"
    assert q.red_img == b"bytes:IMG_RED"      # image straight from the CPRS result
    assert warns == []


def test_red_sticker_not_gated_on_prepack():
    # a NON-prepack PO still gets whatever CPRS confirms (old code forced 无需).
    reqs, _ = resolve_requirements(_Cprs(), "DKNY", [_row(is_prepack=False)])
    q = list(reqs.values())[0]
    assert q.red_sticker and q.red_sticker != "无需"


def test_dim_code_shows_in_red_sticker():
    rows = [_row(po_number="PO1"), _row(po_number="PO2", color_en="X")]
    reqs, _ = resolve_requirements(_Cprs(), "DKNY", rows,
                                   manual={"dim_code": "GL", "dim_codes": {"PO1": "AA"}})
    assert reqs[id(rows[0])].red_sticker == "AA"   # per-PO override
    assert reqs[id(rows[1])].red_sticker == "GL"   # global fallback


def test_context_dedup_one_evaluate_po_per_context():
    cprs = _Cprs()
    rows = [_row(color_en="NAVY"), _row(color_en="CLAY"), _row(color_en="RED")]
    reqs, _ = resolve_requirements(cprs, "DKNY", rows)
    assert len(reqs) == 3 and cprs.calls == 1      # one call for the shared context


def test_no_cprs_and_no_brand_warn():
    _, w1 = resolve_requirements(None, "DKNY", [_row()])
    assert any("not configured" in w for w in w1)
    reqs, w2 = resolve_requirements(_Cprs(), "", [_row()])
    assert reqs == {} and any("without a brand" in w for w in w2)


def test_brand_not_decoded_is_skipped():
    reqs, warns = resolve_requirements(_Cprs(), "UNKNOWN BRAND", [_row()])
    assert reqs == {} and any("not decoded" in w for w in warns)


def test_evaluate_po_failure_warns(monkeypatch):
    # No health() on this fake → pre-check is skipped, so the per-PO miss is what
    # surfaces (a client reachable at pre-check but returning None mid-run).
    import po_extractor.ui_helpers.giii_requirements as gr
    monkeypatch.setattr(gr, "_EVAL_BACKOFF", 0)   # don't sleep in tests
    class _Down(_Cprs):
        def evaluate_po(self, raw):
            self.calls += 1
            return None
    d = _Down()
    reqs, warns = resolve_requirements(d, "DKNY", [_row()])
    assert reqs == {} and any("returned no evaluation" in w for w in warns)
    assert d.calls == gr._EVAL_ATTEMPTS          # retried, not a one-shot give-up


def test_evaluate_po_retries_transient_miss(monkeypatch):
    """A single transient miss (a CPRS blip mid-run) is retried and recovers —
    the PO resolves and no warning is emitted."""
    import po_extractor.ui_helpers.giii_requirements as gr
    monkeypatch.setattr(gr, "_EVAL_BACKOFF", 0)
    class _Flaky(_Cprs):
        def __init__(self):
            super().__init__()
            self.n = 0
        def evaluate_po(self, raw):
            self.n += 1
            if self.n == 1:
                return None                       # first attempt blips
            return super().evaluate_po(raw)       # then recovers
    c = _Flaky()
    reqs, warns = resolve_requirements(c, "DKNY", [_row(warehouse_code="UC")])
    assert len(reqs) == 1 and warns == []
    assert c.n == 2                               # retried once, then succeeded


def test_cprs_down_short_circuits_with_one_reason():
    """A whole-server outage (health() says down) yields ONE actionable line —
    not one ambiguous 'unreachable or empty rule set' per PO — and never even
    calls evaluate_po."""
    class _Outage(_Cprs):
        def health(self):
            return False, "Could not reach CPRS: Connection refused"
        def evaluate_po(self, raw):        # must not be reached
            raise AssertionError("evaluate_po called despite CPRS being down")
    rows = [_row(po_number="PO1"), _row(po_number="PO2")]
    reqs, warns = resolve_requirements(_Outage(), "DKNY", rows)
    assert reqs == {}
    assert len(warns) == 1
    assert "not reachable" in warns[0] and "Connection refused" in warns[0]


def test_healthy_client_is_not_blocked_by_precheck():
    # health() returns ok → resolution proceeds exactly as before.
    class _Up(_Cprs):
        def health(self):
            return True, "CPRS OK"
    reqs, warns = resolve_requirements(_Up(), "DKNY", [_row(warehouse_code="UC")])
    assert len(reqs) == 1 and warns == []


def test_health_that_raises_is_treated_as_up():
    # A health() that itself blows up must never abort resolution.
    class _Flaky(_Cprs):
        def health(self):
            raise RuntimeError("boom")
    reqs, _ = resolve_requirements(_Flaky(), "DKNY", [_row(warehouse_code="UC")])
    assert len(reqs) == 1
