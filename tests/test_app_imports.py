"""Smoke test: verify app.py is parseable without executing Streamlit."""
import ast
import os


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_APP = os.path.join(_ROOT, "app.py")


def test_app_py_is_valid_python():
    with open(_APP, encoding="utf-8") as fh:
        src = fh.read()
    ast.parse(src)


def test_app_py_imports_ui_helpers():
    """Ensure app.py wires through the new ui_helpers package."""
    with open(_APP, encoding="utf-8") as fh:
        src = fh.read()
    assert "ui_helpers" in src, "app.py must import from po_extractor.ui_helpers"


def test_ui_helpers_importable_without_streamlit():
    """The whole ui_helpers package must be Streamlit-free."""
    import po_extractor.ui_helpers as h
    # Spot-check the public API
    assert callable(h.schema_seed_rows)
    assert callable(h.detect_template_header_row)
    assert callable(h.detect_fabric_mapping_columns)
    assert callable(h.se_items_to_buyplan_dfs)
