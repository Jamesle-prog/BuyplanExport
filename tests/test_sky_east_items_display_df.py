"""Regression test: the Contract History item browser table (built by
_build_items_display_df) must show Return Label, same as the Excel output.
"""
from __future__ import annotations

import pandas as pd


class _FakeFabricMasterStore:
    def count(self) -> int:
        return 0

    def get_batch_enrichment(self, _fabric_nos):
        return {}


def test_build_items_display_df_includes_return_label(monkeypatch):
    from ui.sky_east import items_view as iv

    monkeypatch.setattr(iv, "get_fabric_master_store", lambda: _FakeFabricMasterStore())
    monkeypatch.setattr(iv.st.session_state, "get", lambda *_a, **_kw: None, raising=False)

    df_items = pd.DataFrame([{
        "pc_no": "PC1", "contract_no": "C1", "color_name": "Blue",
        "brand": "Anna Field", "zalando_po": "PO1", "config_sku": "SKU1",
        "article_name": "Dress", "colour_code": "503", "total_qty": 10,
        "xs": 0, "s": 5, "m": 5, "l": 0, "xl": 0, "xxl": 0,
        "ex_fty_date": "2026-08-01", "return_label": "Yes",
    }])

    display_df, _col_cfg = iv._build_items_display_df(df_items)

    assert "Return Label" in display_df.columns
    assert display_df["Return Label"].iloc[0] == "Yes"
