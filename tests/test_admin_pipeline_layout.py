"""Regression test for ui/admin_pipeline_layout.py.

A st.data_editor(num_rows="dynamic") column lets an admin add a row and only
partially fill it in; the untouched cells round-trip as NaN (float), not "".
Before the fix, ``str(NaN).strip() == 'nan'`` is truthy, so a half-filled new
row could write the literal string "nan" into the persisted JSON config
(column_map / size_column_map / meta_column_map / fabric_slots). The fix adds
``.fillna("")`` on every edited dataframe immediately after st.data_editor.
"""
from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import po_extractor.exporters.template_config as tc
import ui.admin_pipeline_layout as apl


class _FakePipe:
    pipeline_id = "test_pipe_fix7"
    display_name = "Test Pipe"
    description = "desc"
    template_file = "test_pipe.xlsx"
    config_file = "test_pipe_config.json"
    supports_fabric_slots = True


def _fake_data_editor(df, *args, **kwargs):
    key = kwargs.get("key", "")
    if key.startswith("admin_pipe_cols_"):
        return pd.DataFrame([
            {"Field": "Style",    "Column (A,B,C…)": "B"},
            {"Field": "NewField", "Column (A,B,C…)": float("nan")},  # half-filled new row
        ])
    if key.startswith("admin_pipe_sz_"):
        return pd.DataFrame([
            {"Size": "M",         "Column": "D"},
            {"Size": float("nan"), "Column": float("nan")},          # half-filled new row
        ])
    if key.startswith("admin_pipe_meta_"):
        return pd.DataFrame([
            {"Field": "合同号",    "Column": "E"},
            {"Field": float("nan"), "Column": float("nan")},         # half-filled new row
        ])
    if key.startswith("admin_pipe_slots_"):
        return pd.DataFrame([
            {"row": 2, "body_part": "B",          "hhn": "C",           "key": "E"},
            {"row": 6, "body_part": float("nan"), "hhn": float("nan"), "key": float("nan")},
        ])
    return df


def test_save_layout_strips_nan_instead_of_literal_string(monkeypatch):
    saved_cfg: dict = {}

    monkeypatch.setattr(tc, "list_pipelines", lambda: [_FakePipe()])
    monkeypatch.setattr(tc, "load_config", lambda pid: dict(
        header_row=None, data_start_row=None, write_headers=False,
        column_map={}, size_column_map={}, meta_column_map={},
        fabric_slots=[], fabric_key_field="display_key", notes="",
    ))
    monkeypatch.setattr(tc, "template_exists", lambda pid: False)

    def _fake_save_config(pid, cfg):
        saved_cfg.update(cfg)
        return pid

    monkeypatch.setattr(tc, "save_config", _fake_save_config)
    monkeypatch.setattr(apl.st, "data_editor", _fake_data_editor)

    import streamlit.delta_generator as dg
    orig_button = dg.DeltaGenerator.button

    def _fake_button(self, label, *a, **kwargs):
        return kwargs.get("key", "").startswith("admin_pipe_save_")

    monkeypatch.setattr(dg.DeltaGenerator, "button", _fake_button)
    try:
        apl.show_pipeline_layout_admin()
    finally:
        dg.DeltaGenerator.button = orig_button

    assert saved_cfg, "tc.save_config was never called — Save layout button not detected"

    # column_map: the half-filled "NewField" row must be dropped entirely,
    # not saved as {"NewField": "nan"}.
    assert saved_cfg["column_map"] == {"Style": "B"}
    assert "nan" not in saved_cfg["column_map"].values()

    # size_column_map: the all-NaN row must not become {"NAN": "nan"}.
    assert saved_cfg["size_column_map"] == {"M": "D"}
    assert "NAN" not in saved_cfg["size_column_map"]
    assert "nan" not in saved_cfg["size_column_map"].values()

    # meta_column_map: same story.
    assert saved_cfg["meta_column_map"] == {"合同号": "E"}
    assert "nan" not in saved_cfg["meta_column_map"].values()

    # fabric_slots: row 6 has a valid row number but blank body_part/hhn/key —
    # those must come back as "", never the literal string "nan".
    slots_by_row = {s["row"]: s for s in saved_cfg["fabric_slots"]}
    assert slots_by_row[6]["body_part"] == ""
    assert slots_by_row[6]["hhn"] == ""
    assert slots_by_row[6]["key"] == ""
