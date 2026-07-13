"""GIII requirements resolution service — the CPRS↔buy-plan integration layer.

One call turns buy-plan rows into per-row :class:`RowRequirements` plus a list
of human-readable warnings. This is the "better API" between the CPRS client
and the GIII section: the exporter and the UI both consume resolved
requirements instead of talking to CPRS themselves.

Design points (vs. the first-pass integration that lived in the exporter):

* **Deduped resolution** — rows are grouped by their order context
  ``(warehouse|ship_to, buyer)``; each distinct context is resolved once,
  not once per row.
* **Channel from the account catalog** — the CPRS account's ``account_type``
  decides the evaluate channel (ECOMM / OFF_PRICE / RETAIL / WHOLESALE)
  instead of hardcoding WHOLESALE.
* **Diagnostics are first-class** — every silent fallback (unmatched buyer,
  unresolved warehouse, CPRS unreachable) becomes a warning string the UI
  can show, instead of an invisibly blank cell.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RowRequirements:
    warehouse: str = ""
    region: str = ""           # destination country/region (US/EU/…) from the DC
    channel: str = "WHOLESALE"
    account: str = ""
    red_sticker: str = ""
    carton_mark: str = ""
    prepack_ratio: str = ""
    pcs_box: str = ""
    carton_weight: str = ""    # 箱重限制 (e.g. "40 lbs / 18 kg per carton")
    msrp: str = ""
    rfid: str = ""
    red_img: bytes | None = field(default=None, repr=False)
    mark_img: bytes | None = field(default=None, repr=False)


_CHANNEL_BY_TYPE = (
    ("COMM", "ECOMM"),          # ECOMM / E_COMMERCE
    ("OFF", "OFF_PRICE"),
    ("RETAIL", "RETAIL"),
)


def _channel_for(account_type: str) -> str:
    up = (account_type or "").upper()
    for marker, channel in _CHANNEL_BY_TYPE:
        if marker in up:
            return channel
    return "WHOLESALE"


def _pending(rj: dict) -> str:
    w = (rj or {}).get("waiting_for", "")
    return f"待定:{w}" if w else "待定"


def _yn(v) -> str:
    return "" if v is None else ("Y" if v else "N")


def _red_sticker_text(is_prepack, red_res, dim_code: str) -> str:
    """Red sticker (P). Required only for PREPACK orders — checked first
    (verified live: DKNY's red sticker applies to pre-pack orders and must
    show the DIM code)."""
    if is_prepack is False:
        return "无需"
    if red_res and red_res.get("status") == "not_applicable":
        return "无需"
    if dim_code:
        return dim_code
    rj = (red_res or {}).get("resultJson") or {}
    if red_res and red_res.get("status") == "pending_input":
        return _pending(rj)
    return str(rj.get("code") or rj.get("dim_code") or "")


def _result_text(res) -> str:
    """Carton-mark cell (Q) — status-aware for the real CPRS shapes."""
    if not res:
        return ""
    status = res.get("status")
    if status == "not_applicable":
        return ""
    rj = res.get("resultJson", {}) or {}
    if status == "pending_input":
        return _pending(rj)
    if status == "conflict":
        return "冲突"
    txt = rj.get("value") or rj.get("standard") or rj.get("code")
    if txt:
        return str(txt)
    return "见要求" if rj.get("required") else ""


# An explicit pack-out figure stated in requirement wording, e.g.
# "6 pre-packs per box, 36 pcs/carton" (CK discounter manual).
_PCS_RE = re.compile(r"(\d{1,3})\s*(?:pcs?|pieces?)\s*(?:/|per\s*)(?:carton|ctn|box)",
                     re.IGNORECASE)
_PCS_KEYS = ("pcs_per_carton", "pieces_per_carton", "units_per_carton", "pcs_carton")


def _pcs_from_results(results) -> str:
    """每箱件数 stated by the winning requirements themselves — structured
    keys first, then explicit 'N pcs/carton' wording. Confirmed packaging/
    hangtag/carton results only; nothing is inferred."""
    def _walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if str(k).lower() in _PCS_KEYS and str(x).strip().isdigit():
                    return str(x).strip()
            for x in v.values():
                got = _walk(x)
                if got:
                    return got
        elif isinstance(v, (list, tuple)):
            for x in v:
                got = _walk(x)
                if got:
                    return got
        elif isinstance(v, str):
            m = _PCS_RE.search(v)
            if m:
                return m.group(1)
        return ""

    for res in results or []:
        if res.get("status") == "confirmed" and \
           res.get("domain") in ("packaging", "hangtag", "carton"):
            got = _walk(res.get("resultJson") or {})
            if got:
                return got
    return ""


# Carton weight-limit keys as CPRS states them per client. Three shapes:
# a RANGE ("weight_lbs": "5-40" — CK marking, DKNY VendorNet packing = BOTH
# bounds), upper-only max_* keys (corporate max_weight "40 lbs / 18 kg per
# carton", KL max_weight_lbs / TR098 max_carton_weight_*), and future min_*
# keys. NOT net/gross weight (marking fields), NOT ECT/burst (board
# strength), NOT pallet_spec (pallet, not carton).
_WMAX = {"max_weight": "", "weight_limit": "", "max_gross_weight": "",
         "max_weight_lbs": " lbs", "max_weight_lb": " lbs",
         "max_weight_kg": " kg", "max_carton_weight_lbs": " lbs",
         "max_carton_weight_lb": " lbs", "max_carton_weight_kg": " kg"}
_WMIN = {"min_weight": "", "min_weight_lbs": " lbs", "min_weight_lb": " lbs",
         "min_weight_kg": " kg", "min_carton_weight_lbs": " lbs"}
_WRANGE = {"weight_lbs": " lbs", "weight_lb": " lbs", "weight_kg": " kg",
           "carton_weight_lbs": " lbs"}
_WRANGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*$")


def _weight_from_results(results) -> str:
    """箱重限制 with EXPLICIT bounds, from the winning carton/packaging
    requirements (carton_spec first, pallet_spec excluded). A stated range
    renders both bounds (下限/上限); an upper-only rule renders 上限 alone —
    no claim is made about a lower bound the KB doesn't state."""
    lo, hi = "", ""

    def _walk(v):
        nonlocal lo, hi
        if isinstance(v, dict):
            for k, x in v.items():
                kl = str(k).lower()
                sx = str(x).strip()
                if not sx:
                    continue
                if kl in _WRANGE:
                    m = _WRANGE_RE.match(sx)
                    if m:
                        lo = lo or f"{m.group(1)}{_WRANGE[kl]}".strip()
                        hi = hi or f"{m.group(2)}{_WRANGE[kl]}".strip()
                elif kl in _WMAX:
                    hi = hi or f"{sx}{_WMAX[kl]}".strip()
                elif kl in _WMIN:
                    lo = lo or f"{sx}{_WMIN[kl]}".strip()
            for x in v.values():
                if lo and hi:
                    return
                _walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                if lo and hi:
                    return
                _walk(x)

    ordered = sorted((r for r in results or []
                      if r.get("status") == "confirmed"
                      and r.get("domain") in ("carton", "packaging")
                      and r.get("subtype") != "pallet_spec"),
                     key=lambda r: r.get("subtype") != "carton_spec")
    for res in ordered:
        _walk(res.get("resultJson") or {})
        if lo and hi:
            break
    if lo and hi:
        return f"下限 {lo} / 上限 {hi}"
    if hi:
        return f"上限 {hi}"
    if lo:
        return f"下限 {lo}"
    return ""


def _image_bytes(cprs, res):
    """First linked artwork for a result. CPRS ≥1.6.5 attaches the winning
    requirement's manual artwork as ``images[]`` on every result; older
    responses carried a single ``image_id`` inside resultJson — both work."""
    if not res:
        return None
    imgs = res.get("images") or []
    img_id = imgs[0].get("id") if imgs and isinstance(imgs[0], dict) else None
    if not img_id:
        rj = res.get("resultJson", {}) or {}
        img_id = rj.get("image_id") or rj.get("imageId")
    return cprs.manual_image(img_id) if img_id else None


# A parenthesised pack ratio inside the PO's packing/hanger text, e.g.
# "FLAT PACK + HANGER (1-2-2-1)" — three or more dash-joined counts. Its
# presence means the order is PREPACK even without an explicit PPK marker.
_RATIO_RE = re.compile(r"\(\s*(\d{1,2}(?:\s*-\s*\d{1,2}){2,})\s*\)")


def pack_ratio(*texts) -> str:
    """Extract the prepack ratio from packing/hanger text ('' if none)."""
    for t in texts:
        m = _RATIO_RE.search(str(t or ""))
        if m:
            return re.sub(r"\s+", "", m.group(1))
    return ""


def strip_ratio(text) -> str:
    """Remove the parenthesised ratio from a packing/hanger cell value."""
    return _RATIO_RE.sub("", str(text or "")).strip(" ,;+-·") if text else ""


def prepack_flag(packaging, hanger="") -> bool | None:
    """Is the order prepack, judged from the PO's own packing/hanger text?
    None when the PO carries no packing info at all."""
    packaging = str(packaging or "")
    hanger = str(hanger or "")
    if not (packaging.strip() or hanger.strip()):
        return None
    up = packaging.upper()
    return "PPK" in up or "PREPACK" in up or bool(pack_ratio(packaging, hanger))


# GIII PO numbers START with the division code — a brand marker printed on
# the PO itself, so decoding it is not guessing. Only prefixes documented in
# the CPRS knowledge base are mapped; anything else stays brand-less and
# flagged (e.g. DU… pending confirmation):
#   CSKHHN… = the CK HOL26 Ross vendor faxes (KB open-questions #11/#12/#18)
#   LSKHHN… = KL Ross Perris POE ("KL warehouse code PE. Confirmed from PO
#             LSKHHN series." — KB warehouse-lookup seed)
#   DW…     = DKNY Sportswear (division code DW; DWHHN000DN — KB #13)
PO_PREFIX_BRANDS = {
    "DW": "DKNY Sportswear",
    "CS": "Calvin Klein",
    "LS": "Karl Lagerfeld",
}


def brand_from_po(po_number) -> str:
    """Derive the brand from the PO number's leading division code, using
    only the documented prefix map. Returns '' when the prefix is unknown."""
    po = str(po_number or "").strip().upper()
    if len(po) < 6 or not po[:2].isalpha():
        return ""
    return PO_PREFIX_BRANDS.get(po[:2], "")


def _suffix_warehouse(po_number, codes) -> str:
    """DKNY-style PO numbers end in the DC code (DW867662UC → UC). Only trust
    the suffix when it is one of the client's real warehouse codes — mirrors
    the CPRS engine's warehouseFromSuffix."""
    po = str(po_number or "").strip().upper()
    if len(po) < 4:
        return ""
    suf = po[-2:]
    return suf if suf in codes else ""


def _warehouse_codes(cprs, client_id) -> set:
    codes = set()
    for w in getattr(cprs, "list_warehouses", lambda _cid: [])(client_id) or []:
        c = str(w.get("warehouse_code") or w.get("code") or "").strip().upper()
        if c:
            codes.add(c)
    return codes




def resolve_po_requirements(cprs, pos) -> tuple[list[dict], list[str]]:
    """Resolve the FULL requirement set for freshly-uploaded POs (the
    upload-time requirements document — all domains, not just the buy-plan
    columns).

    *pos* is a list of parsed ``POData``. Returns ``(contexts, warnings)``
    where each context is one PO's order context plus every CPRS result::

        {po_number, style, brand, warehouse, account, channel, results: [...]}

    Order contexts are deduped — POs sharing (brand, warehouse, buyer) reuse
    one evaluation. Graceful: no CPRS / unknown brand → ([], [reason]).
    """
    warnings: list[str] = []
    if cprs is None:
        return [], ["CPRS not configured — no requirements document generated."]
    lc = getattr(cprs, "list_clients", None)
    if lc is not None and not (lc() or []):
        return [], ["CPRS unreachable (or has no clients) — no requirements "
                    "document generated. Check the CPRS server."]

    contexts: list[dict] = []
    eval_cache: dict[tuple, list] = {}
    client_cache: dict[str, str | None] = {}

    for po in pos:
        m = po.metadata
        po_no = m.po_number or "?"
        # Brand: division carries it for GIII PDFs (e.g. "DKNY"), customer as
        # fallback, company last.
        brand = (m.division_name or m.division or "").strip() \
            or brand_from_po(m.po_number) \
            or (m.customer or m.company or "").strip()
        if brand not in client_cache:
            client_cache[brand] = cprs.resolve_client(brand) if brand else None
        client_id = client_cache[brand]
        if not client_id:
            warnings.append(f"PO {po_no}: brand '{brand or '—'}' not found in CPRS "
                            f"— skipped in requirements document.")
            continue

        # Warehouse: the PO's destination code IS the DC code when present;
        # else the PO-number suffix when it is a real DC code; else resolve
        # the ship-to address.
        wh = (m.destination_code or "").strip() \
            or _suffix_warehouse(m.po_number, _warehouse_codes(cprs, client_id)) \
            or (cprs.resolve_warehouse(m.ship_to or "", client_id) or "")
        if not wh:
            warnings.append(f"PO {po_no}: warehouse not resolved — "
                            f"warehouse-level requirements may be missing.")

        buyer = (m.buyer or m.customer or "").strip()
        account = cprs.resolve_account(buyer, client_id) if buyer else None

        acct_type = ""
        if account:   # guard: None == None would adopt an arbitrary row's type
            for a in getattr(cprs, "list_accounts", lambda _c: [])(client_id) or []:
                if (a.get("account_code") or a.get("code")) == account:
                    acct_type = a.get("account_type", "")
                    break

        order = {"clientId": client_id, "channel": _channel_for(acct_type)}
        if wh:
            order["warehouseCode"] = wh
        if account:
            order["accountCode"] = account
        if m.country_of_origin:
            order["coo"] = m.country_of_origin

        ckey = tuple(sorted((k, str(v)) for k, v in order.items()))
        if ckey not in eval_cache:
            eval_cache[ckey] = cprs.evaluate(order)
        results = eval_cache[ckey]
        if not results:
            warnings.append(f"PO {po_no}: CPRS returned no requirements "
                            f"(service unreachable or empty rule set).")

        contexts.append({
            "po_number": po_no, "style": m.style or "",
            "brand": brand, "warehouse": wh, "account": account or "",
            "channel": order["channel"], "results": results,
        })

    return contexts, warnings


def resolve_requirements(cprs, brand: str, rows, manual: dict | None = None,
                         translate=None) -> tuple[dict[int, RowRequirements], list[str]]:
    """Resolve CPRS requirements for buy-plan *rows*.

    Returns ``({id(row): RowRequirements}, warnings)``. With no usable CPRS
    client or an unresolvable brand, the dict is empty and warnings say why —
    the buy plan still generates with those columns blank.
    """
    warnings: list[str] = []
    if cprs is None:
        return {}, ["CPRS not configured — requirement columns left blank."]

    rows = list(rows)
    # No guessing: a PO without a brand keeps every brand-dependent cell
    # blank; the buy plan flags it (the PO can't tell us whose rules apply).
    if not brand:
        return {}, ["POs without a brand — CPRS requirement columns left "
                    "blank; they are flagged in the buy plan."]
    # Distinguish "CPRS is down" from "brand not found" — an unreachable
    # server used to masquerade as a per-brand not-found warning.
    lc = getattr(cprs, "list_clients", None)
    if lc is not None and not (lc() or []):
        return {}, ["CPRS unreachable (or has no clients) — requirement "
                    "columns left blank. Check the CPRS server and "
                    "Admin → Settings."]
    client_id = cprs.resolve_client(brand)
    if not client_id:
        return {}, [f"Brand '{brand}' not found in CPRS — requirement columns left blank."]

    wh_codes = _warehouse_codes(cprs, client_id)

    manual = manual or {}
    global_dim = str(manual.get("dim_code", "") or "").strip()
    # Per-PO DIM codes (POs in one generation can carry different pre-pack
    # codes); the single dim_code acts as the fallback for unlisted POs.
    dim_map = {str(k).strip(): str(v).strip()
               for k, v in (manual.get("dim_codes") or {}).items() if str(v).strip()}
    manual_pcs = str(manual.get("pcs_box", "") or "").strip()

    def dim_for(row) -> str:
        return dim_map.get(str(row.po_number).strip(), global_dim)

    # account code -> type, for channel derivation
    acct_type = {}
    for a in getattr(cprs, "list_accounts", lambda _cid: [])(client_id) or []:
        code = a.get("account_code") or a.get("code")
        if code:
            acct_type[code] = a.get("account_type", "")

    def cn(txt: str) -> str:
        return translate(txt) if (translate and txt) else txt

    out: dict[int, RowRequirements] = {}
    ctx_cache: dict[tuple, RowRequirements] = {}

    for r in rows:
        dim_code = dim_for(r)
        # Resolve the warehouse BEFORE the dedup key — two POs with no stored
        # code but different PO-number suffixes are different contexts.
        wh = (r.warehouse_code
              or _suffix_warehouse(r.po_number, wh_codes)
              or ((cprs.resolve_warehouse(r.ship_to, client_id) or "")
                  if str(r.ship_to or "").strip() else ""))
        ctx_key = (wh or r.ship_to or "", r.buyer or "",
                   bool(r.is_prepack), dim_code)
        cached = ctx_cache.get(ctx_key)
        if cached is not None:
            out[id(r)] = cached
            continue

        if not wh and (r.ship_to or "").strip():
            warnings.append(f"PO {r.po_number}: warehouse not resolved from ship-to "
                            f"'{r.ship_to[:40]}' — MSRP/RFID left blank.")

        account = cprs.resolve_account(r.buyer, client_id) if r.buyer else None
        if r.buyer and not account:
            warnings.append(f"PO {r.po_number}: buyer '{r.buyer}' didn't match a "
                            f"CPRS account — account-level rules skipped.")

        order = {"clientId": client_id,
                 "channel": _channel_for(acct_type.get(account, ""))}
        if wh:
            order["warehouseCode"] = wh
        if account:
            order["accountCode"] = account
        if dim_code:
            order["contextFields"] = {"dim_code": dim_code}

        carton = cprs.carton_results(order)
        results = cprs.evaluate(order)   # cached — same call carton_results made
        flags = cprs.warehouse_flags(client_id, wh) if wh else {"rfid": None, "msrp": None}
        red = carton.get("red_carton_sticker")
        mark = carton.get("carton_marking") or carton.get("warehouse_diamond")

        # Red-sticker artwork can be linked under a sibling subtype
        # (e.g. CK's red_carton_sticker_sizes) — fall back across them.
        red_img = _image_bytes(cprs, red)
        if red_img is None:
            for sub, res in carton.items():
                if sub.startswith("red_carton_sticker"):
                    red_img = _image_bytes(cprs, res)
                    if red_img:
                        break

        ratio, pcs_box = "", ""
        if r.is_prepack and account and hasattr(cprs, "prepack_spec"):
            spec = cprs.prepack_spec(client_id, account)
            ratio, pcs_box = spec.get("ratio", ""), spec.get("pcs_box", "")
            if not ratio:
                warnings.append(f"PO {r.po_number}: no prepack ratio on file for "
                                f"account '{account}'.")
        if not pcs_box:
            # 每箱件数 stated in the winning requirements' own wording
            # (e.g. CK discounter: "6 pre-packs per box, 36 pcs/carton").
            pcs_box = _pcs_from_results(results)

        req = RowRequirements(
            warehouse=wh, region=str(flags.get("region", "") or ""),
            channel=order["channel"], account=account or "",
            red_sticker=_red_sticker_text(r.is_prepack, red, dim_code),
            carton_mark=cn(_result_text(mark)),
            prepack_ratio=ratio if r.is_prepack is not False else "",
            pcs_box=manual_pcs or pcs_box,
            carton_weight=_weight_from_results(results),
            msrp=_yn(flags.get("msrp")), rfid=_yn(flags.get("rfid")),
            red_img=red_img, mark_img=_image_bytes(cprs, mark),
        )
        ctx_cache[ctx_key] = req
        out[id(r)] = req

    return out, warnings
