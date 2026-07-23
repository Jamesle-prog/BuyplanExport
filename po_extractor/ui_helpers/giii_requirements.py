"""GIII requirements resolution service — the CPRS↔buy-plan integration layer.

One call turns buy-plan rows into per-row :class:`RowRequirements` plus a list
of human-readable warnings. This is the "better API" between the CPRS client
and the GIII section: the exporter and the UI both consume resolved
requirements instead of talking to CPRS themselves.

Design points (vs. the first-pass integration that lived in the exporter):

* **CPRS is the single source of truth — no local gates.** One
  ``cprs.evaluate_po(rawPO)`` call DECODES the PO (brand→client, ship-to→
  warehouse, buyer→account, channel, COO) AND evaluates it; the app renders
  the returned results verbatim (status-aware) and builds NO applicability
  gate, derivation, or business rule on top. See
  ``docs/GIII_CPRS_Integration_API.md`` ("Design principle").
* **Deduped resolution** — rows are grouped by their decoded order context
  ``(warehouseCode, shipTo, account, dim_code, coo)``; each distinct context
  is evaluated once, not once per row.
* **Diagnostics are first-class** — every silent fallback (undecoded brand,
  unmatched buyer, CPRS unreachable) becomes a warning string the UI can
  show, instead of an invisibly blank cell.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

# CPRS restarts mid-run more often than we'd like; a single transient miss
# should not drop the whole PO. Retry a few times with a short backoff before
# giving up — free in the happy path (only fires on a miss).
_EVAL_ATTEMPTS = 3
_EVAL_BACKOFF = 0.8   # seconds between attempts


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


def _cprs_down(cprs) -> str:
    """Return the reason string when CPRS is unreachable, else '' (up / unknown).

    Uses the client's ``health()`` (which returns ``(ok, message)``) as a single
    pre-flight probe so a whole-server outage is reported once, with cause,
    instead of one ambiguous line per PO. Clients without ``health()`` (the test
    fakes) are treated as up — their ``evaluate_po`` speaks for itself. A
    health() that itself raises must never break resolution, so failures here
    are swallowed (treated as up; per-PO evaluation still reports real misses).
    """
    hc = getattr(cprs, "health", None)
    if not callable(hc):
        return ""
    try:
        ok, msg = hc()
    except Exception:
        return ""
    return "" if ok else (str(msg or "").strip() or "no response")


def _evaluate_po_resilient(cprs, raw: dict):
    """``cprs.evaluate_po(raw)`` with a bounded retry so a CPRS blip mid-run
    (a restart between POs) doesn't drop a PO that would otherwise resolve.
    Returns the result dict or None after the last attempt. No sleeping when
    the very first attempt succeeds — the retry cost is paid only on a miss."""
    po = cprs.evaluate_po(raw)
    if po:
        return po
    for _ in range(max(0, _EVAL_ATTEMPTS - 1)):
        if _EVAL_BACKOFF > 0:
            try:
                time.sleep(_EVAL_BACKOFF)
            except Exception:
                pass
        po = cprs.evaluate_po(raw)
        if po:
            return po
    return None


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


def _result_for(results, domain, subtypes):
    """First CONFIRMED result for *domain* + *subtype(s)*, else the first one
    present, else None. No app gating — CPRS's own status decides which wins."""
    if isinstance(subtypes, str):
        subtypes = (subtypes,)
    cands = [r for r in (results or [])
             if r.get("domain") == domain and r.get("subtype") in subtypes]
    for r in cands:
        if r.get("status") == "confirmed":
            return r
    return cands[0] if cands else None


def _cell_value(res, dim_code: str = "") -> str:
    """Status-aware buy-plan cell value taken verbatim from a CPRS result. The
    app only maps the field → column; CPRS decides applicability and value
    (no prepack-gating or other local rules)."""
    if not res:
        return ""
    status = res.get("status")
    if status == "not_applicable":
        return "无需"
    rj = res.get("resultJson") or {}
    if status == "pending_input":
        return dim_code or _pending(rj)      # operator's runtime input wins
    if status == "conflict":
        return "冲突"
    v = rj.get("code") or rj.get("value") or rj.get("standard") or dim_code
    return str(v) if v else "见要求"


# An explicit pack-out figure stated in requirement wording, e.g.
# "6 pre-packs per box, 36 pcs/carton" (CK discounter manual).
_PCS_RE = re.compile(r"(\d{1,3})\s*(?:pcs?|pieces?)\s*(?:/|per\s*)(?:carton|ctn|box)",
                     re.IGNORECASE)
_PCS_KEYS = ("pcs_per_carton", "pieces_per_carton", "units_per_carton", "pcs_carton")


def _pcs_from_results(results) -> str:
    """每箱件数 stated by the winning requirements themselves — structured
    keys first, then explicit 'N pcs/carton' wording. Confirmed packaging/
    hangtag/carton results only; nothing is inferred.

    A requirement may state DIFFERENT figures per garment category (CK:
    blouses 36 pcs/carton, jackets 12) and the order context doesn't carry
    the category — every distinct figure is returned ('36/12') rather than
    silently picking whichever clause happens to come first."""
    found: list[str] = []

    def _add(v: str):
        if v and v not in found and len(found) < 4:
            found.append(v)

    def _walk(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if str(k).lower() in _PCS_KEYS and str(x).strip().isdigit():
                    _add(str(x).strip())
            for x in v.values():
                _walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                _walk(x)
        elif isinstance(v, str):
            for m in _PCS_RE.finditer(v):
                _add(m.group(1))

    for res in results or []:
        if res.get("status") == "confirmed" and \
           res.get("domain") in ("packaging", "hangtag", "carton"):
            _walk(res.get("resultJson") or {})
            if found:
                break          # figures from ONE requirement, not mixed sources
    return "/".join(found)


# Carton weight-limit keys as CPRS states them per client. Three shapes:
# a RANGE ("weight_lbs": "5-40" — CK marking, DKNY VendorNet packing = BOTH
# bounds), upper-only max_* keys (corporate max_weight "40 lbs / 18 kg per
# carton", KL max_weight_lbs / TR098 max_carton_weight_*), and future min_*
# keys. NOT net/gross weight (marking fields), NOT ECT/burst (board
# strength), NOT pallet_spec (pallet, not carton).
_WMAX = {"max_weight": "", "weight_limit": "", "max_gross_weight": "",
         "max_weight_lbs": "lbs", "max_weight_lb": "lbs",
         "max_weight_kg": "kg", "max_carton_weight_lbs": "lbs",
         "max_carton_weight_lb": "lbs", "max_carton_weight_kg": "kg"}
_WMIN = {"min_weight": "", "min_weight_lbs": "lbs", "min_weight_lb": "lbs",
         "min_weight_kg": "kg", "min_carton_weight_lbs": "lbs"}
_WRANGE = {"weight_lbs": "lbs", "weight_lb": "lbs", "weight_kg": "kg",
           "carton_weight_lbs": "lbs"}
_WRANGE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*$")
_KG_PER_LB = 0.45359237


def _wnum(x: float) -> str:
    r = round(x, 1)
    return str(int(r)) if r == int(r) else str(r)


def _fmt_weight(raw, unit: str) -> str:
    """Render a weight with its equivalent in the other unit, e.g. 40 lbs →
    '40 lbs (18.1 kg)'. Non-numeric text (e.g. the corporate '40 lbs / 18 kg
    per carton', which already carries both units) passes through as-is."""
    s = str(raw).strip()
    try:
        v = float(s)
    except ValueError:
        # Value already carries its unit ("40 lbs" in a *_lbs key) — don't
        # append it twice.
        return s if (not unit or unit in s.lower()) else f"{s} {unit}"
    # The stated value renders verbatim; only the CONVERTED figure is rounded.
    if unit == "lbs":
        return f"{s} lbs ({_wnum(v * _KG_PER_LB)} kg)"
    if unit == "kg":
        return f"{s} kg ({_wnum(v / _KG_PER_LB)} lbs)"
    return s


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
                        lo = lo or _fmt_weight(m.group(1), _WRANGE[kl])
                        hi = hi or _fmt_weight(m.group(2), _WRANGE[kl])
                elif kl in _WMAX:
                    hi = hi or _fmt_weight(sx, _WMAX[kl])
                elif kl in _WMIN:
                    lo = lo or _fmt_weight(sx, _WMIN[kl])
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


def _all_image_bytes(cprs, res, cache: dict) -> list[bytes]:
    """Every linked artwork for a result (the requirements document embeds them
    all, not just the first). Fetches are deduped through *cache* keyed by image
    id, so an image shared across POs is downloaded once. Best-effort — a client
    without ``manual_image`` or a failed fetch yields fewer/no images, never an
    error."""
    fetch = getattr(cprs, "manual_image", None)
    if fetch is None or not isinstance(res, dict):
        return []
    ids: list[str] = []
    for im in (res.get("images") or []):
        iid = im.get("id") if isinstance(im, dict) else (im if isinstance(im, str) else None)
        if iid and iid not in ids:
            ids.append(iid)
    if not ids:
        rj = res.get("resultJson") or {}
        iid = rj.get("image_id") or rj.get("imageId")
        if iid:
            ids.append(iid)
    out: list[bytes] = []
    for iid in ids:
        if iid not in cache:
            try:
                cache[iid] = fetch(iid)
            except Exception:
                cache[iid] = None
        if cache[iid]:
            out.append(cache[iid])
    return out


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


def brand_of(po_number, division: str = "") -> str:
    """The CPRS-recognizable brand for a PO — what /evaluate/po must receive.

    The parsed division field is often a raw code ("DW") or an abbreviation
    ("DKNY W/SPRTSWR"), and CPRS rejects both with 400 ("Provide clientId or a
    recognizable brand name"). The documented PO-prefix map yields the canonical
    name CPRS accepts ("DW…" → "DKNY Sportswear"), so prefer it; fall back to the
    division text only when the prefix is unknown (best effort for a brand the
    map doesn't cover)."""
    return brand_from_po(po_number) or str(division or "").strip()


def clean_warehouse(code) -> str:
    """Bare DC code for CPRS from the parsed destination code.

    The parser stores the destination with a 'WRH' warehouse prefix
    ('WRHUC' → 'UC', 'WRHDS' → 'DS'). CPRS wants the bare code and does NOT
    resolve the prefixed form (verified: 'WRHUC' → warehouseInfo null, 'UC' →
    resolved) — worse, sending 'WRHUC' overrides CPRS's own PO-suffix decode.
    Strip a leading 'WRH'; a code without it (or blank) passes through."""
    c = str(code or "").strip()
    return c[3:] if len(c) > 3 and c[:3].upper() == "WRH" else c


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




def raw_po_context(m, brand: str) -> dict:
    """The RAW-PO context dict handed to CPRS (``/evaluate/po`` and the
    ``/export/requirements-doc`` API share this shape). The app only passes
    fields through — CPRS decodes brand→client, ship-to→warehouse,
    account→account, channel and COO itself.

    The retail ACCOUNT is the PO's Customer (Macy's / Ross / AM Retail …).
    The buyer field is the G-III vendor entity (G-III Apparel/Leather,
    Kostroma) — never a CPRS account, so sending it only produces a false
    "not matched" warning. When there's no customer, send no account and let
    CPRS apply brand-level defaults silently.
    """
    raw: dict = {"brand": brand, "poNumber": m.po_number or "?"}
    if m.style:
        raw["style"] = m.style
    wh = clean_warehouse(m.destination_code)   # strip the 'WRH' prefix
    if wh:
        raw["warehouseCode"] = wh
    if (m.ship_to or "").strip():
        raw["shipTo"] = m.ship_to
    account = str(getattr(m, "customer", "") or "").strip()
    if account:
        raw["account"] = account
    if (m.country_of_origin or "").strip():
        raw["coo"] = m.country_of_origin
    return raw


def build_requirements_api_requests(pos) -> tuple[list[dict], list[str]]:
    """Prepare ``/export/requirements-doc`` request bodies for parsed *pos*.

    Pure — no CPRS calls — so it can run at upload time and sit in session
    state until the user clicks Generate. POs sharing one order context
    (brand, warehouse, ship-to, account, COO) are grouped into ONE document
    whose ``pos[]`` register lists each PO; the API renders that register
    verbatim and never invents a CPO/MSRP/FOB we didn't send (missing values
    show as 待定 by the API's own rule). Business fields (fob/amount/msrp)
    are always passed — the *variant* chosen at generation time decides
    whether the API renders or strips them; the app takes no view.

    Returns ``(requests, warnings)`` where each request is
    ``{"label": str, "raw": {…/evaluate/po context…}, "pos": [row…]}``.
    At generation time the raw context goes through ``evaluate_po`` first
    (cached since upload) and the DECODED context CPRS returns — clientId,
    channel, warehouseCode, accountCode — is passed to the export endpoint
    verbatim via :func:`export_body_from_decoded`; the app decodes nothing.
    """
    groups: dict[tuple, dict] = {}
    warnings: list[str] = []
    for po in pos:
        m = po.metadata
        po_no = m.po_number or "?"
        brand = brand_of(m.po_number, m.division_name or getattr(m, "division", ""))
        if not brand:
            warnings.append(f"PO {po_no}: no brand on the PO — not in the API "
                            f"requirements document.")
            continue
        ctx = raw_po_context(m, brand)

        colors, sizes = [], []
        total_units = 0
        for sr in (po.size_rows or []):
            c = str(getattr(sr, "color", "") or "").strip()
            if c and c not in colors:
                colors.append(c)
            s = str(getattr(sr, "size", "") or "").strip()
            u = int(getattr(sr, "units", 0) or 0)
            total_units += u
            if s:
                sizes.append(f"{s}×{u}")

        row = {
            "order":          po_no,
            "giiiSalesOrder": po_no,
            "style":          str(m.style or ""),
            "color":          " / ".join(colors),
            "qty":            total_units,
            "sizes":          " ".join(sizes),
            "etd":            str(getattr(m, "factory_ship_date", "") or
                                  getattr(m, "xport_date", "") or "").strip(),
            "cpo":            str(getattr(m, "cpo", "") or "").strip(),
            "msrp":           str(getattr(m, "msrp", "") or "").strip(),
            "fob":            str(getattr(m, "unit_cost", "") or "").strip(),
            "amount":         str(getattr(m, "line_extended_cost", "") or "").strip(),
        }

        gkey = (brand, ctx.get("warehouseCode", ""), ctx.get("shipTo", ""),
                ctx.get("account", ""), ctx.get("coo", ""))
        grp = groups.get(gkey)
        if grp is None:
            # One document per order context; its context comes from the
            # first PO in the group (identical for all by construction,
            # except poNumber/style which are per-PO and travel in pos[]).
            raw = dict(ctx)
            raw.pop("style", None)
            label = " · ".join(p for p in (
                brand, ctx.get("warehouseCode", ""),
                ctx.get("account", "")) if p)
            grp = groups[gkey] = {"label": label or brand, "raw": raw,
                                  "pos": []}
        grp["pos"].append(row)

    requests = [{"label": g["label"], "raw": g["raw"], "pos": g["pos"]}
                for g in groups.values()]
    return requests, warnings


def export_body_from_decoded(decoded: dict) -> dict:
    """The /export/requirements-doc context, taken VERBATIM from
    ``evaluate_po``'s ``decoded`` block (the endpoint validates the
    /evaluate shape: clientId UUID + channel + optional codes). Empty values
    are dropped rather than sent — the app supplies nothing of its own."""
    out: dict = {}
    for src, dst in (("clientId", "clientId"), ("channel", "channel"),
                     ("warehouseCode", "warehouseCode"),
                     ("accountCode", "accountCode"), ("coo", "coo")):
        v = str((decoded or {}).get(src) or "").strip()
        if v:
            out[dst] = v
    return out


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
    if not hasattr(cprs, "evaluate_po"):
        return [], ["CPRS client too old for /evaluate/po — no requirements "
                    "document generated."]
    # One health pre-check so a CPRS OUTAGE yields a single actionable line,
    # not one ambiguous "unreachable or empty rule set" per PO. (health() does
    # its own request and returns WHY it failed.) Duck-typed clients that don't
    # expose health() — the test fakes — just skip straight to evaluation.
    down = _cprs_down(cprs)
    if down:
        return [], [f"CPRS is not reachable ({down}) — requirements document "
                    f"skipped. Start CPRS, then re-generate."]

    contexts: list[dict] = []
    img_cache: dict[str, bytes | None] = {}   # image id → bytes (fetched once)

    for po in pos:
        m = po.metadata
        po_no = m.po_number or "?"
        # Brand off the PO only, normalized to a name CPRS accepts — the parsed
        # division is often a raw code ("DW") that CPRS 400s on, so brand_of()
        # prefers the documented PO-prefix → canonical-brand map. No guessing.
        brand = brand_of(m.po_number, m.division_name or getattr(m, "division", ""))
        if not brand:
            warnings.append(f"PO {po_no}: no brand on the PO — skipped in the "
                            f"requirements document.")
            continue

        # Hand CPRS the RAW PO; /evaluate/po decodes brand→client, ship-to→
        # warehouse, account→account, channel, COO — and evaluates it.
        raw = raw_po_context(m, brand)

        po_ev = _evaluate_po_resilient(cprs, raw)
        if not po_ev:
            warnings.append(f"PO {po_no}: CPRS returned no evaluation — skipped "
                            f"(transient error, or CPRS went down mid-run).")
            continue
        decoded = po_ev.get("decoded") or {}
        results = (po_ev.get("evaluation") or {}).get("results") or []
        if not decoded.get("clientId"):
            warnings.append(f"PO {po_no}: brand '{brand}' not decoded by CPRS "
                            f"— skipped in the requirements document.")
            continue
        for w in (decoded.get("warnings") or []):
            warnings.append(f"PO {po_no}: {w}")

        # Attach ALL linked artwork bytes to each result (deduped, idempotent).
        for res in results or []:
            if isinstance(res, dict) and "_images" not in res:
                res["_images"] = _all_image_bytes(cprs, res, img_cache)

        whinfo = decoded.get("warehouseInfo") or {}
        units = sum(int(getattr(sr, "units", 0) or 0) for sr in (po.size_rows or []))
        packing = " · ".join(p for p in (
            str(getattr(m, "packaging", "") or "").strip(),
            str(getattr(m, "hanger", "") or "").strip()) if p)

        contexts.append({
            "po_number": po_no, "style": m.style or "", "brand": brand,
            # decoded context — CPRS resolved these
            "warehouse": str(decoded.get("warehouseCode") or ""),
            "account": str(decoded.get("accountCode") or ""),
            "channel": str(decoded.get("channel") or "WHOLESALE"),
            "region": str(whinfo.get("region", "") or ""),
            "results": results,
            # PO Index / Pre-pack enrichment
            "units": units,
            "article": (str(getattr(m, "style_description", "") or "").strip()
                        or str(getattr(m, "fabric", "") or "").strip()),
            "destination": str(getattr(m, "ship_to", "") or "").strip(),
            "packing": packing,
            "msrp": str(getattr(m, "msrp", "") or "").strip(),
            "coo": str(getattr(m, "country_of_origin", "") or "").strip(),
            "source_file": str(getattr(m, "file_name", "") or "").strip(),
            "is_prepack": prepack_flag(getattr(m, "packaging", ""),
                                       getattr(m, "hanger", "")),
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
    if not hasattr(cprs, "evaluate_po"):
        return {}, ["CPRS client too old for /evaluate/po — requirement "
                    "columns left blank."]
    down = _cprs_down(cprs)
    if down:
        return {}, [f"CPRS is not reachable ({down}) — requirement columns left "
                    f"blank. Start CPRS, then re-generate."]

    manual = manual or {}
    global_dim = str(manual.get("dim_code", "") or "").strip()
    dim_map = {str(k).strip(): str(v).strip()
               for k, v in (manual.get("dim_codes") or {}).items() if str(v).strip()}
    manual_pcs = str(manual.get("pcs_box", "") or "").strip()

    def cn(txt: str) -> str:
        return translate(txt) if (translate and txt) else txt

    out: dict[int, RowRequirements] = {}
    cache: dict[tuple, RowRequirements] = {}

    for r in rows:
        dim_code = dim_map.get(str(r.po_number).strip(), global_dim)
        # Hand CPRS the RAW PO — /evaluate/po DECODES brand→client,
        # ship-to→warehouse, buyer→account, channel and COO itself, then
        # evaluates. The app no longer resolves or gates any of that.
        raw: dict = {"brand": brand, "poNumber": str(r.po_number or "")}
        if getattr(r, "style", ""):
            raw["style"] = r.style
        wh = clean_warehouse(r.warehouse_code)   # strip the 'WRH' prefix
        if wh:
            raw["warehouseCode"] = wh
        if str(r.ship_to or "").strip():
            raw["shipTo"] = r.ship_to
        if str(r.buyer or "").strip():          # account text (customer-first; see _buyplan)
            raw["account"] = r.buyer
        if getattr(r, "coo", ""):
            raw["coo"] = r.coo
        if dim_code:
            raw["contextFields"] = {"dim_code": dim_code}

        ckey = (raw.get("warehouseCode", ""), raw.get("shipTo", ""),
                raw.get("account", ""), dim_code, raw.get("coo", ""))
        cached = cache.get(ckey)
        if cached is not None:
            out[id(r)] = cached
            continue

        po = _evaluate_po_resilient(cprs, raw)
        if not po:
            warnings.append(f"PO {r.po_number}: CPRS returned no evaluation — "
                            f"requirement columns left blank (transient error, "
                            f"or CPRS went down mid-run).")
            continue
        decoded = po.get("decoded") or {}
        results = (po.get("evaluation") or {}).get("results") or []
        if not decoded.get("clientId"):
            warnings.append(f"PO {r.po_number}: brand '{brand}' not decoded by "
                            f"CPRS — requirement columns left blank.")
            continue
        for w in (decoded.get("warnings") or []):
            warnings.append(f"PO {r.po_number}: {w}")

        whinfo = decoded.get("warehouseInfo") or {}
        red = _result_for(results, "carton", "red_carton_sticker")
        mark = _result_for(results, "carton", ("carton_marking", "warehouse_diamond"))
        prepk = _result_for(results, "packaging", ("pre_pack_ratio", "prepack"))
        # Every requirement value is rendered straight from CPRS — NO local
        # gate (not prepack, not warehouse, not channel, not anything). If CPRS
        # returns a pack ratio / pcs-per-carton, it shows; if not, the cell is
        # blank. CPRS's own status decides applicability, never an app-side PO
        # fact. See docs/GIII_CPRS_Integration_API.md ("Design principle").
        ratio = str((prepk or {}).get("resultJson", {}).get("ratio", "")
                    or (prepk or {}).get("resultJson", {}).get("alpha", "") or "")

        req = RowRequirements(
            # decoded context — CPRS resolved these, not the app
            warehouse=str(decoded.get("warehouseCode") or r.warehouse_code or ""),
            region=str(whinfo.get("region", "") or "").upper(),
            channel=str(decoded.get("channel") or "WHOLESALE"),
            account=str(decoded.get("accountCode") or ""),
            # values verbatim from CPRS results (status-aware); the red sticker
            # is whatever CPRS confirms — no prepack gating.
            red_sticker=_cell_value(red, dim_code),
            carton_mark=cn(_cell_value(mark)),
            prepack_ratio=ratio,                                # from CPRS, no gate
            pcs_box=manual_pcs or _pcs_from_results(results),   # from CPRS, all orders
            carton_weight=_weight_from_results(results),
            # MSRP/RFID defaults from CPRS's decoded warehouseInfo
            msrp=_yn(whinfo.get("msrp_required_default")),
            rfid=_yn(whinfo.get("rfid_default")),
            red_img=_image_bytes(cprs, red),
            mark_img=_image_bytes(cprs, mark),
        )
        cache[ckey] = req
        out[id(r)] = req

    return out, warnings
