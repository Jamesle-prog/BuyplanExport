"""Apply an emailed spreadsheet to the system.

:mod:`inbound_router` decides *what* a file is and previews it;
this module is the only place that actually writes. Separating the two is
what makes "always review" real — nothing here runs until a person clicks
Apply in the 📧 Email tab.

Every applier returns the same shape::

    {"ok": bool, "applied": int, "skipped": int, "messages": [str, ...]}

so the UI renders one result panel regardless of file type. Applying the
same file twice is safe: progress reports are a dated log (duplicates are
visible, not destructive) and milestone/plan writes are idempotent
overwrites of the same cells.

Fabric lists are deliberately NOT applied here — they go through the
existing propose/approve peer-review queue, which is a stronger gate than
this one and must not be bypassed just because a file arrived by email.
"""
from __future__ import annotations

from .inbound_router import (
    KIND_BUYPLAN, KIND_FABRIC_LIST, KIND_HHN_PROGRESS, KIND_PROGRESS_FORM,
)


def _result(ok=True, applied=0, skipped=0, messages=None) -> dict:
    return {"ok": ok, "applied": applied, "skipped": skipped,
            "messages": messages or []}


def _apply_progress_form(content: bytes, username: str, factory: str) -> dict:
    from ..exporters.factory_progress_form import parse_progress_report_xlsx
    from ..store import get_factory_progress_store, get_production_tracking_store

    parsed = parse_progress_report_xlsx(content, factory=factory)
    fp, pt = get_factory_progress_store(), get_production_tracking_store()
    msgs = list(parsed.get("issues") or [])
    applied = skipped = 0

    for rp in parsed.get("reports") or []:
        try:
            fp.add_report(
                rp["po_number"], rp["style"], rp["stage"], rp["report_date"],
                rp["units"], factory=rp["factory"], source="email",
                notes=rp["notes"], created_by=username,
            )
            applied += 1
        except ValueError as exc:
            skipped += 1
            msgs.append(f"{rp['po_number']} / {rp['style']}: {exc}")

    for m in parsed.get("milestones") or []:
        fields: dict = {}
        if m["expected"]:
            fields[f"{m['stage']}_planned"] = m["expected"]
        if m["note"]:
            fields[f"{m['stage']}_notes"] = m["note"]
        if m["completed"]:
            fields[f"{m['stage']}_actual"] = m["completed"]
            fields[f"{m['stage']}_status"] = "Done"
        if not fields:
            continue
        try:
            if pt.update_stage_fields(m["po_number"], m["style"], fields,
                                      updated_by=username):
                applied += 1
            else:
                skipped += 1
                msgs.append(f"{m['po_number']} / {m['style']}: not tracked — "
                            "add it in 🏭 Tracking first.")
        except ValueError as exc:
            skipped += 1
            msgs.append(f"{m['po_number']} / {m['style']}: {exc}")

    return _result(True, applied, skipped, msgs)


def _apply_buyplan(content: bytes, username: str) -> dict:
    """Returned buy plan Index tab → planned milestone dates.

    The Index keys rows by (客人PC NO, 款号) while tracking keys by
    (PO, style), so PC+style is resolved to a PO through sky_east_items.
    Blank cells never erase a stored value.
    """
    from ..exporters.factory_progress_form import parse_buyplan_index_tracking
    from ..store import get_production_tracking_store, get_sky_east_store

    rows = (parse_buyplan_index_tracking(content) or {}).get("rows") or []
    pt = get_production_tracking_store()
    msgs: list[str] = []
    applied = skipped = 0

    po_map: dict = {}
    try:
        for _, r in get_sky_east_store().list_items().iterrows():
            key = (str(r.get("pc_no") or "").strip(),
                   str(r.get("style") or "").strip())
            po = str(r.get("zalando_po") or "").strip()
            if all(key) and po and key not in po_map:
                po_map[key] = po
    except Exception as exc:
        msgs.append(f"Could not read Sky East items to resolve PO numbers: {exc}")

    for row in rows:
        po = po_map.get((row["pc_no"], row["style"]), "")
        if not po:
            skipped += 1
            msgs.append(f"{row['pc_no']} / {row['style']}: no PO found for this "
                        "PC + style.")
            continue
        fields = {f"{k}_planned": v for k, v in (row["planned"] or {}).items()}
        if row.get("factory"):
            fields["factory"] = row["factory"]
        if not fields:
            continue
        try:
            if pt.update_stage_fields(po, row["style"], fields,
                                      updated_by=username):
                applied += 1
            else:
                skipped += 1
                msgs.append(f"{po} / {row['style']}: not tracked — skipped.")
        except ValueError as exc:
            skipped += 1
            msgs.append(f"{po} / {row['style']}: {exc}")

    return _result(True, applied, skipped, msgs)


def _apply_hhn_progress(content: bytes, source: str) -> dict:
    """大货进度表 → progress_records, upserted.

    Upsert (never replace-all): an emailed file is usually a partial update,
    and wiping a company's whole progress table because someone mailed one
    sheet would be a much bigger action than the sender intended.
    """
    from ..lookups.progress_lookup import parse_progress_rows
    from ..store import get_po_store

    records = parse_progress_rows(content)
    if not records:
        return _result(False, messages=["No progress rows found in this file."])
    n = get_po_store().save_progress_records_batch(source or "sky_east", records)
    return _result(True, int(n or 0), len(records) - int(n or 0),
                   [f"Progress records upserted for {source or 'sky_east'}."])


def apply_attachment(content: bytes, kind: str, *, username: str = "",
                     factory: str = "", source: str = "sky_east") -> dict:
    """Write an emailed workbook into the system. Never raises."""
    try:
        if kind == KIND_PROGRESS_FORM:
            return _apply_progress_form(content, username, factory)
        if kind == KIND_BUYPLAN:
            return _apply_buyplan(content, username)
        if kind == KIND_HHN_PROGRESS:
            return _apply_hhn_progress(content, source)
        if kind == KIND_FABRIC_LIST:
            return _result(
                False, messages=[
                    "Fabric lists are not applied from email. Upload the file "
                    "in 🧵 Fabric DB so it goes through the approval queue."],
            )
        return _result(False, messages=["This file type cannot be applied."])
    except Exception as exc:
        return _result(False, messages=[f"Could not apply the file: {exc}"])
