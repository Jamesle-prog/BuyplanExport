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

from dataclasses import dataclass, field


@dataclass
class RowRequirements:
    warehouse: str = ""
    channel: str = "WHOLESALE"
    account: str = ""
    red_sticker: str = ""
    carton_mark: str = ""
    prepack_ratio: str = ""
    pcs_box: str = ""
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


def _image_bytes(cprs, res):
    if not res:
        return None
    rj = res.get("resultJson", {}) or {}
    img_id = rj.get("image_id") or rj.get("imageId")
    return cprs.manual_image(img_id) if img_id else None


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
    if not brand:
        return {}, ["No brand on this buy plan — CPRS lookup skipped."]

    client_id = cprs.resolve_client(brand)
    if not client_id:
        return {}, [f"Brand '{brand}' not found in CPRS — requirement columns left blank."]

    manual = manual or {}
    dim_code = str(manual.get("dim_code", "") or "").strip()
    manual_pcs = str(manual.get("pcs_box", "") or "").strip()

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
        ctx_key = (r.warehouse_code or r.ship_to or "", r.buyer or "", bool(r.is_prepack))
        cached = ctx_cache.get(ctx_key)
        if cached is not None:
            out[id(r)] = cached
            continue

        wh = r.warehouse_code or (cprs.resolve_warehouse(r.ship_to, client_id) or "")
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
        flags = cprs.warehouse_flags(client_id, wh) if wh else {"rfid": None, "msrp": None}
        red = carton.get("red_carton_sticker")
        mark = carton.get("carton_marking") or carton.get("warehouse_diamond")

        ratio, pcs_box = "", ""
        if r.is_prepack and account and hasattr(cprs, "prepack_spec"):
            spec = cprs.prepack_spec(client_id, account)
            ratio, pcs_box = spec.get("ratio", ""), spec.get("pcs_box", "")
            if not ratio:
                warnings.append(f"PO {r.po_number}: no prepack ratio on file for "
                                f"account '{account}'.")

        req = RowRequirements(
            warehouse=wh, channel=order["channel"], account=account or "",
            red_sticker=_red_sticker_text(r.is_prepack, red, dim_code),
            carton_mark=cn(_result_text(mark)),
            prepack_ratio=ratio if r.is_prepack is not False else "",
            pcs_box=(manual_pcs or pcs_box) if r.is_prepack is not False else manual_pcs,
            msrp=_yn(flags.get("msrp")), rfid=_yn(flags.get("rfid")),
            red_img=_image_bytes(cprs, red), mark_img=_image_bytes(cprs, mark),
        )
        ctx_cache[ctx_key] = req
        out[id(r)] = req

    return out, warnings
