"""Pure-logic formatting of POStore save results into status messages.

Keeps the Streamlit-side caller in app.py thin: this module returns the lines
to write and the summary; the caller renders them with `st.write` / appends
HTML to the run log.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormattedLine:
    """One status line, with both plain (UI) and HTML (log) variants."""
    status: str          # "new" | "duplicate" | "updated" | "skipped"
    po_number: str
    plain: str           # for st.write
    html: str            # for log entries


@dataclass(frozen=True)
class FormattedSaveLog:
    counts: dict[str, int]
    lines: list[FormattedLine]
    summary_plain: str
    summary_html: str
    skipped_po_numbers: list[str]   # POs that need a save_exception() call


def format_save_results(results: list[tuple]) -> FormattedSaveLog:
    """Format a list of (po_number, status, diff) tuples into renderable lines.

    Status values understood: "new", "duplicate", "updated", "skipped".
    For "updated" rows, *diff* must be a dict with keys "old" and "new",
    each holding "version" and "total_units".
    """
    counts = {"new": 0, "duplicate": 0, "updated": 0, "skipped": 0}
    lines: list[FormattedLine] = []
    skipped: list[str] = []

    for po_number, status, diff in results:
        if status not in counts:
            continue
        counts[status] += 1

        if status == "new":
            plain = f"  💾 {po_number} — saved to history"
            html = f"💾 <b>{po_number}</b> saved to history"
        elif status == "duplicate":
            plain = f"  ♻️ {po_number} — identical copy already in history, skipped"
            html = f"♻️ <b>{po_number}</b> identical duplicate, skipped"
        elif status == "updated":
            old, new = diff["old"], diff["new"]
            delta = new["total_units"] - old["total_units"]
            sign = f"+{delta}" if delta >= 0 else str(delta)
            plain = (
                f"  🔄 {po_number} — **updated** "
                f"(version {old['version']} → {new['version']}, "
                f"units {old['total_units']} → {new['total_units']} [{sign}])"
            )
            html = (
                f"🔄 <b>{po_number}</b> updated: version "
                f"{old['version']} → {new['version']}, "
                f"units {old['total_units']} → {new['total_units']} ({sign})"
            )
        else:   # skipped
            plain = "  ⚠️ one PO had no PO number — skipped"
            html = f"⚠️ <b>{po_number or '(blank)'}</b> skipped — missing PO number"
            skipped.append(po_number)

        lines.append(FormattedLine(status, po_number, plain, html))

    summary = (
        f"{counts['new']} new, {counts['updated']} updated, "
        f"{counts['duplicate']} duplicate(s) skipped"
    )
    return FormattedSaveLog(
        counts=counts,
        lines=lines,
        summary_plain=f"  📊 Store summary: {summary}",
        summary_html=f"📊 Store: {summary}",
        skipped_po_numbers=skipped,
    )
