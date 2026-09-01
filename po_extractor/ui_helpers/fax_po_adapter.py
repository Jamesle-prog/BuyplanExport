"""Fax-format PO dicts → the standard ``POData`` the store already holds.

The four fax sections of the GIII Upload tab (KL, MSG/CSKHHA, TK EU, Infor
Nexus) each parse their own PDF layout, but all four return the *same* 17-key
dict — po_number / style / po_date / ship_date / etd / vendor / factory /
fob_price / description / line_items / customer_name / ship_to / hanger_info /
pack_ratio / hts_num / cpo / msrp — so one adapter serves all of them.

Until now those results only ever became a downloadable workbook and were
never saved, which is why a fax PO could not appear in the Order Summary or
the PO Tracker beside the main GIII flow and Sky East: both read the database,
and nothing had put a fax PO there. Converting to ``POData`` puts them through
the same ``save_many_checked`` path as every other PO, so they inherit its
duplicate detection, revision history and conflict reporting for free.

Pure data mapping, no Streamlit and no store — so it is unit-testable and the
UI layer only has to hand over what it already parsed.
"""
from __future__ import annotations

from ..models.po_data import POData, POMetadata, SizeRow

# The parsers write "?" for a field they could not find, and "UNCONFIRMED"
# for a price the fax explicitly marks as not yet agreed. Neither is a value;
# both become None so the column reads empty rather than carrying a token
# that would then be exported and totalled as if it were real.
_NOT_A_VALUE = {"", "?", "??", "n/a", "N/A", "-", "unconfirmed", "UNCONFIRMED"}


def _v(value) -> str | None:
    """A real value, or None for the parsers' missing-field placeholders."""
    if value is None:
        return None
    s = str(value).strip()
    return None if s in _NOT_A_VALUE or s.lower() in _NOT_A_VALUE else s


def fax_po_to_podata(po: dict, *, company: str = "GIII",
                     source_format: str = "", processed_by: str = "",
                     source_file_hash: str = "") -> POData | None:
    """One parsed fax PO dict → ``POData``; None when it has no PO number.

    A PO number is the store's identity for a record, so a dict without one
    is skipped rather than saved under an empty key where it would collide
    with every other unidentified PO.

    ``etd`` becomes each size row's ``xfty_date``: the store's size-row key is
    (po, style, colour, size, xfty_date), so carrying it keeps a re-issued PO
    with a new ex-factory date as its own rows instead of silently overwriting
    the first shipment's.
    """
    po_number = _v(po.get("po_number"))
    if not po_number:
        return None

    etd = _v(po.get("etd")) or ""
    meta = POMetadata(
        po_number=po_number,
        style=_v(po.get("style")),
        po_date=_v(po.get("po_date")),
        vendor=_v(po.get("vendor")),
        factory=_v(po.get("factory")),
        hanger=_v(po.get("hanger_info")),
        ship_to=_v(po.get("ship_to")),
        customer=_v(po.get("customer_name")),
        style_description=_v(po.get("description")),
        unit_cost=_v(po.get("fob_price")),
        factory_ship_date=_v(po.get("ship_date")),
        xport_date=etd or None,
        ratio=_v(po.get("pack_ratio")),
        msrp=_v(po.get("msrp")),
        cpo=_v(po.get("cpo")),
        company=company,
        source_format=source_format or None,
        file_name=_v(po.get("source_file")),
        processed_by=processed_by or None,
        source_file_hash=source_file_hash or None,
    )

    rows: list[SizeRow] = []
    for item in po.get("line_items") or []:
        style = _v(item.get("style")) or meta.style or ""
        color = _v(item.get("color")) or ""
        for entry in item.get("sizes") or []:
            # (size, units, upc, price) — price is per-size and often None on
            # continuation lines, where the line's first price applies.
            try:
                size, units, upc = entry[0], entry[1], entry[2]
            except (TypeError, IndexError):
                continue
            try:
                units = int(units)
            except (TypeError, ValueError):
                continue
            rows.append(SizeRow(
                po_number=po_number, style=style, color=color,
                size=str(size or "").strip(), units=units,
                upc=str(upc or "").strip(), xfty_date=etd,
            ))

    return POData(metadata=meta, size_rows=rows)


def fax_pos_to_podata(results: list[dict], **kw) -> list[POData]:
    """Convert a section's whole parse result; dicts with no PO number are
    dropped (see :func:`fax_po_to_podata`)."""
    out = []
    for po in results or []:
        converted = fax_po_to_podata(po, **kw)
        if converted is not None:
            out.append(converted)
    return out
