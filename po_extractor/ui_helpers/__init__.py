"""Pure-logic helpers extracted from app.py for testability.

These modules contain no Streamlit dependencies. Each function can be
imported and unit-tested in isolation, providing a regression net before
larger UI refactors.
"""
from po_extractor.ui_helpers.schema import (
    schema_seed_rows, load_live_schema, save_live_schema,
    live_label_for, live_client_label_for,
)
from po_extractor.ui_helpers.template_detect import (
    detect_template_header_row, make_sample_buyplan_template,
)
from po_extractor.ui_helpers.fabric_mapping_detect import (
    detect_fabric_mapping_columns,
    STYLE_COL_KEYWORDS, BODY_PART_KEYWORDS, CODE_KEYWORDS,
)
from po_extractor.ui_helpers.sky_east_buyplan import (
    SE_SIZE_COLS, se_items_to_buyplan_dfs,
)
from po_extractor.ui_helpers.color_enrichment import enrich_cn_color
from po_extractor.ui_helpers.save_log import (
    FormattedLine, FormattedSaveLog, format_save_results,
)
from po_extractor.ui_helpers.excel_format import write_excel_header_row
from po_extractor.ui_helpers.excel_reports import (
    SIZE_ORDER, generate_color_plan_excel, generate_po_summary_excel,
)
from po_extractor.ui_helpers.fabric_mapping_parse import parse_fabric_mapping_rows
from po_extractor.ui_helpers.wash_label import write_wash_label_excel
from po_extractor.ui_helpers.dual_header import (
    DUAL_HEADER_STATIC, get_dual_header, write_dual_header_excel,
)
from po_extractor.ui_helpers.fabric_mapping_template import (
    generate_fabric_mapping_template, BODY_PART_LIST,
)

__all__ = [
    "schema_seed_rows", "load_live_schema", "save_live_schema",
    "live_label_for", "live_client_label_for",
    "detect_template_header_row", "make_sample_buyplan_template",
    "detect_fabric_mapping_columns",
    "STYLE_COL_KEYWORDS", "BODY_PART_KEYWORDS", "CODE_KEYWORDS",
    "SE_SIZE_COLS", "se_items_to_buyplan_dfs",
    "enrich_cn_color",
    "FormattedLine", "FormattedSaveLog", "format_save_results",
    "write_excel_header_row",
    "SIZE_ORDER", "generate_color_plan_excel", "generate_po_summary_excel",
    "parse_fabric_mapping_rows",
    "write_wash_label_excel",
    "DUAL_HEADER_STATIC", "get_dual_header", "write_dual_header_excel",
    "generate_fabric_mapping_template", "BODY_PART_LIST",
]
