from .buyplan_export import export_buyplan
from .csv_export import export_csvs
from .color_plan_export import export_color_plan
from .po_summary_export import export_po_summary
from .cross_check_export import export_cross_check
from .hhp_buyplan_export import export_hhp_buyplan
from .hhp_template_p_export import export_hhp_template_p
from .sky_east_buyplan_export import (
    export_sky_east_buyplan,
    export_sky_east_nukuryou,
    check_nukuryou_ready,
    build_cross_comparison,
)

__all__ = [
    "export_csvs", "export_buyplan", "export_color_plan",
    "export_po_summary", "export_cross_check",
    "export_hhp_buyplan", "export_hhp_template_p",
    "export_sky_east_buyplan", "export_sky_east_nukuryou",
    "check_nukuryou_ready", "build_cross_comparison",
]

# ---------------------------------------------------------------------------
# Format registry — register the 4 core PDF-pipeline output formats
# ---------------------------------------------------------------------------
from .registry import OutputFormat, register

register(OutputFormat("buy_plan",    "1.0", "Buy Plan",    "PO×Color×Size per style sheet",          "transformed_data_by_style_filtered_with_totals_and_metadata", ".xlsx", export_buyplan))
register(OutputFormat("color_plan",  "1.0", "Color Plan",  "Color×Size pivot per style tab",          "color_plan_by_style", ".xlsx", export_color_plan))
register(OutputFormat("po_summary",  "1.0", "PO Summary",  "One row per PO+Color with metadata",      "po_summary",          ".xlsx", export_po_summary))
register(OutputFormat("cross_check", "1.0", "Cross Check", "Unit reconciliation across all outputs",  "cross_check",         ".xlsx", export_cross_check))
