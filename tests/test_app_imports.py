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


def test_no_ui_module_uses_SK_without_importing_it():
    """Guard against the class of runtime NameError where a module references
    `SK.*` inside a function but never imports SK (a missing import isn't
    caught by module-import smoke tests). This bit giii_view.py: SK used in
    the upload-detection cache with no import, only crashing on that path."""
    import glob
    offenders = []
    for path in glob.glob(os.path.join(_ROOT, "ui", "**", "*.py"), recursive=True):
        if path.endswith(os.sep + "session_keys.py"):
            continue  # the definition module itself
        with open(path, encoding="utf-8-sig") as fh:   # tolerate a BOM
            src = fh.read()
        if "SK." not in src:
            continue
        tree = ast.parse(src)
        imports_sk = any(
            (isinstance(n, ast.ImportFrom) and any(a.name == "SK" for a in n.names))
            or (isinstance(n, ast.Import) and any(a.name.endswith("SK") for a in n.names))
            for n in ast.walk(tree)
        )
        # also allow `SK` bound as a module-level name (e.g. alias assignment)
        assigns_sk = any(
            isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "SK" for t in n.targets)
            for n in ast.walk(tree)
        )
        if not (imports_sk or assigns_sk):
            offenders.append(os.path.relpath(path, _ROOT))
    assert not offenders, f"modules use SK.* without importing SK: {offenders}"
