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
    """Ensure app.py wires the live schema through the ui_helpers package —
    since v2.125.4 via ui/schema_labels.py (the one app-wide schema cache)."""
    import os
    with open(_APP, encoding="utf-8") as fh:
        src = fh.read()
    assert "ui.schema_labels" in src, "app.py must use ui.schema_labels for the live schema"
    labels = os.path.join(os.path.dirname(_APP), "ui", "schema_labels.py")
    with open(labels, encoding="utf-8") as fh:
        assert "po_extractor.ui_helpers" in fh.read(), \
            "ui/schema_labels.py must load the schema via po_extractor.ui_helpers"


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
        tree = ast.parse(src)
        # A REAL SK.attr access — an Attribute whose value is the name `SK`.
        # (String checks false-positive on docs/changelog text containing "SK.".)
        uses_sk = any(
            isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == "SK"
            for n in ast.walk(tree)
        )
        if not uses_sk:
            continue
        bound = any(
            (isinstance(n, ast.ImportFrom) and any(a.name == "SK" for a in n.names))
            or (isinstance(n, ast.Import) and any(a.name.endswith("SK") for a in n.names))
            or (isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "SK" for t in n.targets))
            for n in ast.walk(tree)
        )
        if not bound:
            offenders.append(os.path.relpath(path, _ROOT))
    assert not offenders, f"modules use SK.* without importing SK: {offenders}"


def test_no_module_calls_t_without_binding_it():
    """Same class as the SK guard, for the i18n `t()` helper — a `t(...)` call
    in a module that never imports/binds `t` is a runtime NameError only hit
    on that code path (it crashed the upload progress bar). Covers ui/ and
    po_extractor/."""
    import glob
    offenders = []
    for path in (glob.glob(os.path.join(_ROOT, "ui", "**", "*.py"), recursive=True)
                 + glob.glob(os.path.join(_ROOT, "po_extractor", "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8-sig") as fh:
            tree = ast.parse(fh.read())
        calls_t = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                      and n.func.id == "t" for n in ast.walk(tree))
        if not calls_t:
            continue
        bound = False
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and any((a.asname or a.name) == "t" for a in n.names):
                bound = True
            elif isinstance(n, ast.Assign) and any(
                    isinstance(x, ast.Name) and x.id == "t" for x in n.targets):
                bound = True
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                    a.arg == "t" for a in n.args.args + n.args.kwonlyargs):
                bound = True
            elif isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id == "t":
                bound = True
        if not bound:
            offenders.append(os.path.relpath(path, _ROOT))
    assert not offenders, f"modules call t() without importing t: {offenders}"
