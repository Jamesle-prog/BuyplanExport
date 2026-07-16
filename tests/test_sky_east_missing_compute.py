"""Regression test for ui/sky_east/_missing_compute.py's ``_fill_cno`` guard.

``_compute_se_missing_df`` is wrapped in ``@st.cache_data(ttl=15)``, and
Streamlit's cache does NOT cache raised exceptions -- so before this fix, an
unguarded ``pl.get_contract_no(...)`` call crashed the Missing Fields tab on
every rerun that hit this code path (any widget interaction anywhere in the
Sky East tab), not just "until the TTL clears". The fix wraps the call in a
try/except that falls back to the row's existing ``cno``.
"""
from __future__ import annotations

import pandas as pd
import pytest


def test_compute_se_missing_df_survives_get_contract_no_raising(monkeypatch):
    from ui.sky_east import _missing_compute as mc

    items = pd.DataFrame([{
        "pc_no": "P1", "zalando_po": "PO1", "style": "STY1",
        "color_name": "Navy", "brand": "Anna Field",
        "fabric_item_no": "", "contract_no": "", "ex_fty_date": "2026-08-01",
        "total_qty": 100, "picture_id": "",
    }])

    class _FakeStore:
        def list_items(self):
            return items

    class _BoomLookup:
        def get_contract_no(self, *a, **kw):
            raise RuntimeError("progress file is corrupt")

    def _fake_enrich(df):
        out = df.copy()
        out["composition_en"] = ""
        out["cuttable_width_cm"] = 0
        return out

    monkeypatch.setattr(mc, "get_sky_east_store", lambda: _FakeStore())
    monkeypatch.setattr("ui.sky_east._shared.get_progress_lookup", lambda: _BoomLookup())
    monkeypatch.setattr("ui.sky_east.items_view._enrich_items_df", _fake_enrich)

    mc._compute_se_missing_df.clear()
    # Must not raise -- falls back to the existing (blank) contract_no instead.
    df = mc._compute_se_missing_df()
    assert list(df["contract_no"]) == [""]
