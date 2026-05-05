"""Multi-file Excel combiner for client PO spreadsheets.

Handles:
  1. Multiple files → merged DataFrame, exact-duplicate rows removed.
  2. Repeat orders — same Style + ConfigSKU + Color appearing under DIFFERENT
     PO numbers.  These are kept as separate rows (the PO number distinguishes
     them) and flagged in a ``_repeat_order`` column.
  3. Cross-file conflict detection — same (PO, ConfigSKU, Color, Size) key
     present in two files with *different* quantities → warning returned.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd

from .client_excel import parse_client_excel_to_df, SIZE_COLUMNS

# Deduplication key: same PO + same config + same color = same order line
_DEDUP_KEY = ["Purchase Order Number", "Config SKU", "Main Supplier Color Description"]
_CONFLICT_KEY = _DEDUP_KEY  # same level for quantity conflict check

# Repeat-order grouping key: style + config + color (PO may differ)
_REPEAT_KEY = ["Main Supplier Config SKU", "Config SKU", "Main Supplier Color Description"]


@dataclass
class CombineResult:
    df: pd.DataFrame                       # unified, deduplicated DataFrame
    repeat_orders: dict[str, list[str]]    # style → [po1, po2, …] for repeats
    conflicts: list[str]                   # human-readable conflict messages
    source_files: list[str]                # files that were actually read
    skipped_files: list[str] = field(default_factory=list)  # files that failed


def combine_excel_files(
    paths: list[str],
    sheet_name: str = "1.1.PO_Client",
    *,
    prefer_latest: bool = True,
) -> CombineResult:
    """Parse and merge multiple client Excel files into one CombineResult.

    Parameters
    ----------
    paths        : list of file paths to parse.
    sheet_name   : mapping sheet name (default ``1.1.PO_Client``).
    prefer_latest: when the same row key exists in multiple files and quantities
                   differ, keep the version from the *last* file in the list.
                   Set False to raise a warning and keep the first occurrence.
    """
    frames: list[pd.DataFrame] = []
    source_files: list[str] = []
    skipped: list[str] = []

    for path in paths:
        try:
            df = parse_client_excel_to_df(path, sheet_name=sheet_name)
            if not df.empty:
                frames.append(df)
                source_files.append(os.path.basename(path))
        except Exception as exc:
            skipped.append(f"{os.path.basename(path)}: {exc}")

    if not frames:
        return CombineResult(
            df=pd.DataFrame(),
            repeat_orders={},
            conflicts=[],
            source_files=source_files,
            skipped_files=skipped,
        )

    combined = pd.concat(frames, ignore_index=True)

    # ── Normalise key columns ──────────────────────────────────────────────────
    for col in _DEDUP_KEY + ["Main Supplier Config SKU"]:
        if col in combined.columns:
            combined[col] = combined[col].astype(str).str.strip()

    # ── Conflict detection ─────────────────────────────────────────────────────
    conflicts: list[str] = []
    available_key = [c for c in _CONFLICT_KEY if c in combined.columns]
    size_cols_present = [s for s in SIZE_COLUMNS if s in combined.columns]

    if available_key and size_cols_present:
        grp = combined.groupby(available_key, dropna=False)[size_cols_present]
        for key_vals, sub in grp:
            if len(sub) > 1:
                first = sub.iloc[0][size_cols_present].tolist()
                for i in range(1, len(sub)):
                    row_qtys = sub.iloc[i][size_cols_present].tolist()
                    if row_qtys != first:
                        src_files = sub["_source_file"].tolist() if "_source_file" in sub.columns else []
                        conflicts.append(
                            f"Quantity mismatch for "
                            f"{dict(zip(available_key, key_vals if isinstance(key_vals, tuple) else (key_vals,)))} "
                            f"across files {src_files}. "
                            f"{'Kept latest.' if prefer_latest else 'Kept first.'}"
                        )
                        break

    # ── Deduplication ──────────────────────────────────────────────────────────
    dedup_key = [c for c in _DEDUP_KEY if c in combined.columns]
    if dedup_key:
        keep = "last" if prefer_latest else "first"
        combined = combined.drop_duplicates(subset=dedup_key, keep=keep)
    combined = combined.reset_index(drop=True)

    # ── Repeat-order detection ─────────────────────────────────────────────────
    repeat_orders: dict[str, list[str]] = {}
    repeat_key = [c for c in _REPEAT_KEY if c in combined.columns]
    po_col = "Purchase Order Number"
    style_col = "Main Supplier Config SKU"

    if repeat_key and po_col in combined.columns and style_col in combined.columns:
        for group_vals, sub in combined.groupby(repeat_key, dropna=False):
            po_numbers = sub[po_col].dropna().unique().tolist()
            if len(po_numbers) > 1:
                style_val = str(sub[style_col].iloc[0]) if style_col in sub.columns else str(group_vals)
                if style_val not in repeat_orders:
                    repeat_orders[style_val] = []
                for po in po_numbers:
                    if po not in repeat_orders[style_val]:
                        repeat_orders[style_val].append(po)

    # Mark repeat-order rows
    combined["_repeat_order"] = False
    if repeat_orders and po_col in combined.columns and style_col in combined.columns:
        for style_val, pos in repeat_orders.items():
            mask = (
                (combined[style_col].astype(str) == style_val) &
                (combined[po_col].astype(str).isin([str(p) for p in pos]))
            )
            combined.loc[mask, "_repeat_order"] = True

    return CombineResult(
        df=combined,
        repeat_orders=repeat_orders,
        conflicts=conflicts,
        source_files=source_files,
        skipped_files=skipped,
    )


def repeat_order_summary(result: CombineResult) -> list[str]:
    """Return human-readable lines describing each repeat-order group."""
    lines = []
    for style, pos in result.repeat_orders.items():
        lines.append(
            f"Style {style!r} appears in {len(pos)} PO(s): {', '.join(str(p) for p in pos)}"
        )
    return lines
