"""Shared constants and low-level display helpers for the Fabric DB tab."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from ui.shared import XLSX_MIME, CSV_MIME  # noqa: F401  (re-exported for sub-modules)

# ---------------------------------------------------------------------------
# Column rename maps (module-level to avoid re-allocating each render)
# ---------------------------------------------------------------------------

FABRIC_DB_LIST_RENAME = {
    "quality_no":        "公司面料编号",
    "erp_code":          "ERP编码",
    "supplier":          "供应商",
    "composition_en":    "面料成分（英文）",
    "weight_gsm":        "克重 GSM",
    "cuttable_width_cm": "有效门幅 CM",
    "dyeing_process":    "印染工艺",
    "shrinkage_rate":    "烫缩率",
    "short_rate":        "短码率",
    "notes_cn":          "备注说明",
    "display_key":       "综合标识 Key",
}

FABRIC_DB_DETAIL_RENAME = {
    "quality_no": "公司面料编号", "erp_code": "ERP编码",
    "supplier_no": "供应商面料编号", "supplier": "供应商",
    "composition_en": "面料成分（英文）", "composition_cn": "面料成分（中文）",
    "yarn_count": "纱支", "structure_en": "面料结构（英文）",
    "structure_cn": "面料结构（中文）", "weight_gsm": "克重 GSM",
    "full_width_cm": "全门幅 CM", "cuttable_width_cm": "有效门幅 CM",
    "dyeing_process": "印染工艺", "moq_y": "MOQ（Y）",
    "moq_setup_fee": "上机费(￥)", "mcq_y": "MCQ（Y）",
    "mcq_small_fee": "小缸费(￥)",
    "is_in_stock": "是否有现货",
    "spot_price_kg": "现货价格(￥/KG)", "spot_price_m": "现货价格(￥/M)",
    "cost_per_kg": "定金价格(￥/KG)", "cost_per_m": "定金价格(￥/M)",
    "quote_date": "报价时间",
    "shrinkage_rate": "烫缩率", "short_rate": "短码率",
    "notes_cn": "备注说明", "notes_en": "Note",
    "quote_history": "报价记录", "display_key": "综合标识 Key",
    "imported_at": "导入时间", "source_file": "来源文件",
}

FABRIC_DB_PAGE_SIZE = 200   # records per page

# ---------------------------------------------------------------------------
# Low-level display helpers
# ---------------------------------------------------------------------------

def _fabric_db_stats_bar(count: int, last) -> None:
    """Render the 3-column stats bar (count / last import / source file)."""
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Fabrics", f"{count:,}")
    c2.metric("Last Import", last["imported_at"][:10] if last else "—")
    c3.metric("Source File", last["source_file"] if last else "—")


def _fabric_db_list_table(df: pd.DataFrame) -> None:
    """Render the browseable fabric list dataframe."""
    show_cols = [c for c in FABRIC_DB_LIST_RENAME if c in df.columns]
    st.dataframe(
        df[show_cols].rename(columns=FABRIC_DB_LIST_RENAME),
        use_container_width=True,
        hide_index=True,
        column_config={
            "综合标识 Key": st.column_config.TextColumn(
                "综合标识 Key",
                help="公司面料编号 | 面料成分（英文） | 克重GSM | 有效门幅CM",
                width="large",
            ),
            "克重 GSM": st.column_config.NumberColumn(format="%.0f"),
            "有效门幅 CM": st.column_config.NumberColumn(format="%.0f"),
            "烫缩率": st.column_config.NumberColumn(format="%.2f"),
            "短码率": st.column_config.NumberColumn(format="%.2f"),
        },
    )
