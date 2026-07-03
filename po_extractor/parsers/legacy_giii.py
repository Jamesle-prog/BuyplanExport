"""Legacy G-III PO parser (ported from PO_Scan_Output_GIII_Combined.py)."""
import os
import re

from ..config import (
    CNTRY_OF_ORIGIN_PATTERN, CUSTOMER_NAME_PATTERN, FACTORY_PATTERN,
    FORMAT_LEGACY, FULL_PATTERN,
    GIII_DESCRIPTION_PATTERN, HANGER_PATTERN, ISSUED_BY_PATTERN, LN_START,
    PO_DATE_PATTERN, PO_NUMBER_PATTERN, SHIP_ADDR1_PATTERN, SHIP_CITY_PATTERN,
    SIZE_PATTERN, STYLE_PATTERN, UNITS_PATTERN, VEND_CNTRY_PATTERN, VENDOR_PATTERN,
    # New extraction patterns
    SEASON_PATTERN, INCOTERM_PATTERN, PORT_PATTERN,
    FOB_PRICE_PATTERN, TARIFF_PATTERN, FABRIC_PATTERN, COMPOSITION_PATTERN,
    XPORT_DATE_PATTERN, HTS_PATTERN, DISCOUNT_PATTERN, PACK_PATTERN,
    VENDOR_NAME_PATTERN,
    # Multi-brand patterns (KL / CK / DKNY)
    BRAND_CODE_PATTERN, KL_FOB_PATTERN, MSRP_PATTERN, CPO_PATTERN,
    PPK_PATTERN, KL_HANGER_PATTERN, KL_DESC_PATTERN,
)
from ..models import POData, POMetadata, SizeRow

PARSER_VERSION = "1.0"


def _score_confidence(meta: POMetadata) -> int:
    """Return confidence 0–100. Deduct 10 for each missing key field."""
    key_fields = [
        meta.po_number,
        meta.factory,
        meta.country_of_origin,
        meta.xport_date,
        meta.division_code,
        meta.style,
    ]
    missing = sum(1 for f in key_fields if not f)
    return max(0, 100 - missing * 10)


def _search(pattern, text, group=1):
    m = re.search(pattern, text)
    return m.group(group).strip() if m else None


def _extract_metadata(text: str, file_path: str) -> POMetadata:
    factory_num = _search(FACTORY_PATTERN, text, 1)
    factory_name = _search(FACTORY_PATTERN, text, 2)
    factory = f"{factory_num} - {factory_name}" if factory_num and factory_name else None

    # ── Brand detection ────────────────────────────────────────────────────────
    brand_code = _search(BRAND_CODE_PATTERN, text)
    is_kl = (brand_code == 'KL')
    is_ck = bool(brand_code and brand_code.startswith('CK'))

    # ── Hanger info (brand-specific) ──────────────────────────────────────────
    hanger = None
    if is_kl:
        # KL: the HANGER keyword lives on the DESCRIPTION line
        # e.g. "DESCRIPTION EMBELLISHED CREW SHO ROSS H25 HANGER"
        hm = re.search(KL_HANGER_PATTERN, text)
        if hm:
            hanger = hm.group(1).strip()
    else:
        # DKNY / CK: standalone "Hanger" / "HANGER" line
        hm = re.search(HANGER_PATTERN, text)
        if hm:
            hanger = hm.group(1).strip()

    # ── Description code (brand-specific) ─────────────────────────────────────
    desc_code = None
    if is_kl:
        # KL: text between DESCRIPTION and HANGER on the same line
        raw = _search(KL_DESC_PATTERN, text)
        if raw:
            desc_code = raw.strip()
    else:
        # DKNY / CK: backreference dedup (apostrophe-aware pattern handles CK)
        desc_code = _search(GIII_DESCRIPTION_PATTERN, text)

    # ── Customer name and Ship To address ─────────────────────────────────────
    customer_name = _search(CUSTOMER_NAME_PATTERN, text)
    addr1 = _search(SHIP_ADDR1_PATTERN, text)
    city  = _search(SHIP_CITY_PATTERN, text)
    if customer_name and addr1 and city:
        ship_to = f"{customer_name} / {addr1} / DISTRIBUTION CENTER / {city}"
    else:
        ship_to = customer_name  # fallback: name only

    # ── Season / incoterm / port ───────────────────────────────────────────────
    season   = _search(SEASON_PATTERN, text)
    inco     = _search(INCOTERM_PATTERN, text)
    port     = _search(PORT_PATTERN, text)
    incoterm = f"{inco} {port}" if inco and port else inco

    # ── FOB price (brand-specific) ────────────────────────────────────────────
    fob_price = None
    if is_kl:
        # KL prints two prices: full price and W/TARIFF price — use W/TARIFF
        fob_price = _search(KL_FOB_PATTERN, text)
    if fob_price is None:
        # DKNY: "FOB: 3.45"  |  CK: "FOB: $3.60"  |  KL fallback
        fob_price = _search(FOB_PRICE_PATTERN, text)

    # ── MSRP (KL only) ────────────────────────────────────────────────────────
    msrp = _search(MSRP_PATTERN, text) if is_kl else None

    # ── CPO / customer PO ref ─────────────────────────────────────────────────
    cpo_raw = _search(CPO_PATTERN, text)
    if cpo_raw:
        cpo = cpo_raw.rstrip('.')
    else:
        # DKNY PDFs don't print a CPO line — default to TBA for output
        cpo = 'TBA'

    tariff    = _search(TARIFF_PATTERN, text)

    # Fabric name + composition
    fabric      = _search(FABRIC_PATTERN, text)
    composition = _search(COMPOSITION_PATTERN, text)
    style_desc  = None
    if fabric:
        style_desc = f"{fabric}  {composition}" if composition else fabric

    # ETD / xport date from item line (first occurrence)
    xport_raw = _search(XPORT_DATE_PATTERN, text)
    if xport_raw:
        # Normalise "8/01/26" → "8/01/2026" if 2-digit year
        parts = xport_raw.split("/")
        if len(parts) == 3 and len(parts[2]) == 2:
            xport_raw = f"{parts[0]}/{parts[1]}/20{parts[2]}"

    # HTS — only from the HTS SUMMARY PAGE section
    hts = None
    hts_idx = text.find("HTS SUMMARY PAGE")
    if hts_idx >= 0:
        hts = _search(HTS_PATTERN, text[hts_idx:hts_idx + 400])

    # Discount — only prefix a leading-dot fraction (".75%" → "0.75%").
    # The old `not startswith("0.")` guard also mangled whole-number
    # discounts: "1.5%" → "0.1.5%", "1%" → "0.1%" (silently 10× smaller).
    discount = _search(DISCOUNT_PATTERN, text)
    if discount and discount.startswith("."):
        discount = "0" + discount

    # Pack type
    packaging = _search(PACK_PATTERN, text)

    # Vendor full name
    seller = _search(VENDOR_NAME_PATTERN, text)
    if seller:
        seller = seller.strip()

    return POMetadata(
        po_number=_search(PO_NUMBER_PATTERN, text),
        style=_search(STYLE_PATTERN, text),
        vendor=_search(VENDOR_PATTERN, text),
        seller=seller,
        issued_by=_search(ISSUED_BY_PATTERN, text),
        po_date=_search(PO_DATE_PATTERN, text),
        vendor_country=_search(VEND_CNTRY_PATTERN, text),
        factory=factory,
        country_of_origin=_search(CNTRY_OF_ORIGIN_PATTERN, text),
        hanger=hanger,
        source_format=FORMAT_LEGACY,
        file_name=os.path.basename(file_path),
        file_path=file_path,
        # Commercial fields
        season=season,
        incoterm=incoterm,
        unit_cost=fob_price,            # FOB selling price per unit
        line_extended_cost=tariff,      # cost / tariff per unit
        style_description=style_desc,   # fabric name + composition
        style_group=hts,                # HTS tariff code
        discount=discount,
        packaging=packaging,
        xport_date=xport_raw,
        factory_ship_date=xport_raw,
        description_code=desc_code,
        customer=customer_name,
        ship_to=ship_to,
        # Multi-brand fields
        msrp=msrp,
        cpo=cpo,
        fabric=fabric,
    )


def _extract_size_rows(text: str, meta: POMetadata) -> tuple[list[SizeRow], list[list]]:
    size_rows: list[SizeRow] = []
    summary: list[list] = []
    start = False
    current_color = None

    for line in text.splitlines():
        if line.startswith(LN_START):
            start = True
            # The first item row may be on the same line as the header
            # (pypdfium2 reading-order output merges them). Don't skip —
            # fall through so FULL_PATTERN can still match on this line.
        if not start:
            continue

        m = re.search(FULL_PATTERN, line)
        if m:
            color, size, units, upc = m.group(1), m.group(2), int(m.group(3)), m.group(4)
            size_rows.append(SizeRow(meta.po_number, meta.style, color, size, units, upc))
            current_color = color
            continue

        if "TTL" in line:
            hanger = line.split("TTL")[0].strip()
            summary.append([meta.po_number, meta.style, current_color, hanger])

        sm = re.search(SIZE_PATTERN, line)
        if sm:
            um = re.search(UNITS_PATTERN, line)
            if um:
                size_rows.append(SizeRow(
                    meta.po_number, meta.style,
                    current_color or "",  # BUG-13: current_color can be None before first FULL_PATTERN match
                    sm.group(1), int(um.group(1)), um.group(2),
                ))

    return size_rows, summary


def parse(text: str, file_path: str) -> POData:
    meta = _extract_metadata(text, file_path)
    size_rows, summary = _extract_size_rows(text, meta)

    meta.parser_version = PARSER_VERSION
    meta.parse_confidence = _score_confidence(meta)
    meta.validation_status = (
        "valid" if (meta.parse_confidence or 0) >= 70 and size_rows
        else ("exception" if not size_rows else "warning")
    )

    return POData(metadata=meta, size_rows=size_rows, summary_rows=summary)
