"""Backend validation for parsed Sky East contracts.

Pure functions, no Streamlit — the UI layer formats/translates the results.
Moved out of ui/sky_east/_validators.py (pipeline-convergence phase 2) so the
Sky East pipeline grades its own data the way the GIII parsers do, and other
consumers (exception queue, reports, tests) can reuse the checks.
"""
from __future__ import annotations

import re
from datetime import datetime

_HHN_RE = re.compile(r'^[A-Za-z]{2,5}-[A-Za-z]{1,5}-?\d{4,8}$')

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
                 "%Y/%m/%d", "%d.%m.%Y")

# Issue-category keys, in display order. The UI maps these to translated
# labels; keep the keys stable — they are part of the return contract.
ISSUE_CATEGORIES = [
    ("missing_style_color", "Missing style/color"),
    ("negative_qty",        "Negative size quantities"),
    ("bad_hhn",             "Non-standard HHN format"),
    ("bad_ex_fty_date",     "Unparseable ex_fty_date"),
]


def validate_contracts(contracts) -> dict:
    """Run item-level quality checks over parsed contracts.

    Returns::

        {
          "total_items":      int,
          "sku_covered":      int,     # items with a non-blank config_sku
          "sku_coverage_pct": float,   # 0.0 when there are no items
          "issues": {category_key: [message, ...], ...},
        }
    """
    issues: dict[str, list[str]] = {key: [] for key, _ in ISSUE_CATEGORIES}
    n_total = n_sku = 0

    for contract in contracts:
        for item in contract.items:
            n_total += 1
            if not (item.style and item.style.strip()):
                issues["missing_style_color"].append(
                    f"PC {contract.pc_no}: item with blank style")
            if not (item.color_name and item.color_name.strip()):
                issues["missing_style_color"].append(
                    f"PC {contract.pc_no}: {item.style} -- blank color_name")
            neg_szs = [f"{s}:{q}" for s, q in (item.sizes or {}).items() if q < 0]
            if neg_szs:
                issues["negative_qty"].append(
                    f"PC {contract.pc_no}: {item.style}/{item.color_name} "
                    f"-- negative qty: {', '.join(neg_szs)}")
            hhn = (item.fabric_item_no or "").strip()
            if hhn and not _HHN_RE.match(hhn):
                issues["bad_hhn"].append(
                    f"PC {contract.pc_no}: {item.style}/{item.color_name} "
                    f"-- HHN '{hhn}' does not match expected format")
            dt_raw = (item.ex_fty_date or "").strip()
            if dt_raw and not _parseable_date(dt_raw):
                issues["bad_ex_fty_date"].append(
                    f"PC {contract.pc_no}: {item.style} "
                    f"-- ex_fty_date '{dt_raw}' could not be parsed")
            if item.config_sku and item.config_sku.strip():
                n_sku += 1

    return {
        "total_items":      n_total,
        "sku_covered":      n_sku,
        "sku_coverage_pct": round(100 * n_sku / n_total, 1) if n_total else 0.0,
        "issues":           issues,
    }


def _parseable_date(raw: str) -> bool:
    for fmt in _DATE_FORMATS:
        try:
            datetime.strptime(raw, fmt)
            return True
        except ValueError:
            pass
    return False
