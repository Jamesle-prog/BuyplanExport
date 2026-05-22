"""Consistency checker for KL-format Excel output.

Compares the generated workbook against the source DataFrames so that
silent data-loss bugs (dropped pivot rows, NaN filtering, etc.) are caught
immediately after generation rather than discovered manually.

Usage
-----
    from po_extractor.ui_helpers.kl_consistency import check_kl_excel

    issues = check_kl_excel(df_meta, df_sizes, kl_bytes)
    if issues:
        for msg in issues:
            print("  ❌", msg)
    else:
        print("  ✅  consistency OK")
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    pass


def check_kl_excel(
    df_meta: pd.DataFrame,
    df_sizes: pd.DataFrame,
    excel_bytes: bytes,
    *,
    verbose: bool = True,
) -> list[str]:
    """Return a list of consistency issues (empty list = all OK).

    Checks performed
    ----------------
    1. PO count  — distinct PO numbers in DB vs PO Detail sheet
    2. Grand total units — DB sum vs PO Detail grand-total row
    3. Per-PO unit totals — DB per-PO sum vs Excel per-PO sum
    4. Summary grand total — PO Detail grand total vs Summary grand total
    5. Missing POs — POs in DB that are absent from the Excel entirely
    """
    issues: list[str] = []

    # ── DB ground-truth ───────────────────────────────────────────────────────
    if df_sizes is None or df_sizes.empty:
        issues.append("DB: df_sizes is empty — nothing to check")
        return issues

    # Normalise column names (POStore returns capitalised names)
    sz = df_sizes.rename(columns={
        "PO Number": "po_number",
        "Style":     "style",
        "Color":     "color",
        "Size":      "size",
        "Units":     "units",
        "UPC":       "upc",
    }).copy()
    sz["units"] = pd.to_numeric(sz["units"], errors="coerce").fillna(0).astype(int)

    db_po_units: dict[str, int] = (
        sz.groupby("po_number")["units"].sum().to_dict()
    )
    db_total: int = sum(db_po_units.values())
    db_pos: set[str] = set(db_po_units)

    # ── Read back the generated Excel ─────────────────────────────────────────
    try:
        xl = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=None, header=None)
    except Exception as exc:
        issues.append(f"Cannot parse generated Excel: {exc}")
        return issues

    # ── Sheet 1: PO Detail ────────────────────────────────────────────────────
    if "PO Detail" not in xl:
        issues.append("Sheet 'PO Detail' not found in workbook")
        return issues

    detail_raw = xl["PO Detail"]

    # Row 0 = header; last row = GRAND TOTAL
    header_row = detail_raw.iloc[0].tolist()
    try:
        po_col    = header_row.index("PO Number")
        units_col = header_row.index("Units")
    except ValueError as exc:
        issues.append(f"PO Detail header column not found: {exc}")
        return issues

    data_rows = detail_raw.iloc[1:]            # drop header
    grand_row  = data_rows[data_rows.iloc[:, po_col] == "GRAND TOTAL"]
    data_rows  = data_rows[data_rows.iloc[:, po_col] != "GRAND TOTAL"]

    # Per-PO unit sums from Excel
    excel_units_col = data_rows.iloc[:, units_col]
    excel_po_col    = data_rows.iloc[:, po_col]
    xl_po_units: dict[str, int] = (
        data_rows.groupby(excel_po_col)[excel_units_col.name]
        .sum()
        .astype(int)
        .to_dict()
    )
    xl_total: int = sum(xl_po_units.values())
    xl_pos: set[str] = set(xl_po_units)

    # Check 1 — PO count
    if len(db_pos) != len(xl_pos):
        issues.append(
            f"PO count mismatch: DB has {len(db_pos)}, Excel has {len(xl_pos)}"
        )

    # Check 2 — Grand total
    if db_total != xl_total:
        issues.append(
            f"Grand total mismatch: DB={db_total:,}  Excel={xl_total:,}"
            f"  diff={db_total - xl_total:+,}"
        )

    # Check 3 — Per-PO
    for pn, db_u in sorted(db_po_units.items()):
        xl_u = xl_po_units.get(pn, 0)
        if db_u != xl_u:
            issues.append(
                f"  {pn}: DB={db_u:,}  Excel={xl_u:,}  diff={db_u - xl_u:+,}"
            )

    # Check 4 — Missing POs
    missing = db_pos - xl_pos
    if missing:
        issues.append(f"POs in DB missing from Excel: {sorted(missing)}")

    extra = xl_pos - db_pos
    if extra:
        issues.append(f"POs in Excel not in DB: {sorted(extra)}")

    # Check 5 — Summary sheet sanity
    if "Summary" in xl:
        summary_raw = xl["Summary"]

        # 5a — Row-count sanity: Summary Part A should have at most
        #       (PO count × 50) data rows.  If it has far more, a
        #       cartesian-product expansion (e.g. dropna=False bug) has
        #       occurred and the sheet is effectively unusable.
        summary_data = summary_raw[
            (summary_raw.iloc[:, 0] != "GRAND TOTAL")
            & summary_raw.iloc[:, 0].notna()
            & (summary_raw.iloc[:, 0].astype(str).str.strip() != "")
            # skip the Part B header row (it may say "Style" etc.)
        ]
        max_expected_rows = max(len(db_pos) * 50, 200)
        if len(summary_data) > max_expected_rows:
            issues.append(
                f"Summary row count explosion: {len(summary_data):,} data rows "
                f"(expected <= {max_expected_rows} for {len(db_pos)} PO(s)).  "
                f"Likely cause: dropna=False cartesian-product in pivot_table."
            )

        # 5b — Grand total in Part A
        gt_rows = summary_raw[summary_raw.iloc[:, 0] == "GRAND TOTAL"]
        if not gt_rows.empty:
            # Total Units is the last numeric value in the first GRAND TOTAL row
            last_gt_row = gt_rows.iloc[0].tolist()
            numeric_vals = [v for v in last_gt_row if isinstance(v, (int, float))
                            and not (isinstance(v, float) and v != v)]
            if numeric_vals:
                summary_total = int(numeric_vals[-1])
                if summary_total != xl_total:
                    issues.append(
                        f"Summary grand total ({summary_total:,}) != "
                        f"Detail grand total ({xl_total:,})"
                    )

    # ── Grand-total row cross-check ───────────────────────────────────────────
    if not grand_row.empty:
        gt_units_cell = grand_row.iloc[0, units_col]
        try:
            gt_units = int(gt_units_cell)
            if gt_units != xl_total:
                issues.append(
                    f"Detail GRAND TOTAL row ({gt_units:,}) != "
                    f"sum of data rows ({xl_total:,})"
                )
        except (TypeError, ValueError):
            issues.append(f"Cannot parse GRAND TOTAL units cell: {gt_units_cell!r}")

    if verbose:
        if issues:
            print(f"[kl_consistency] FAIL  {len(issues)} issue(s) found:")
            for msg in issues:
                print(f"   {msg}")
        else:
            print(
                f"[kl_consistency] OK -- "
                f"{len(db_pos)} PO(s), {db_total:,} units match exactly"
            )

    return issues
