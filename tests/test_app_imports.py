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


def test_no_function_shadows_the_module_level_t():
    """Guard against the sibling of the check above: a function-local `from
    ui.i18n import t` inside a file that ALREADY imports t at module level.

    Assigning (or importing) a name ANYWHERE in a function body makes Python
    treat it as local for the WHOLE function -- so a redundant local `t`
    import doesn't just do nothing extra, it turns every t(...) call
    elsewhere in that same function into a read of a not-yet-bound local.
    That bit ui/sky_east/processing.py: t was already imported at the top of
    the file, but one function ALSO re-imported it locally inside its except
    block, and the very first real upload that hit a brand-new brand crashed
    with "cannot access local variable 't'" the moment it tried to log that
    finding -- a message that only that specific upload shape reaches, so
    nothing before it had exercised the broken line.

    Deliberately does not try to prove a specific local import is safe by
    checking whether it comes before or after each t() call in that function
    -- control flow (if/else, try/except) makes that unreliable to determine
    statically. If a name is already available at module scope, re-importing
    it locally is never needed and is banned outright here, which is also
    simply the fix: delete the redundant import.

    A file with NO module-level t import is unaffected (see ui/memory.py,
    which has no top-level import and legitimately imports t once, first
    thing, inside the one function that uses it).
    """
    import glob
    offenders = []
    for path in (glob.glob(os.path.join(_ROOT, "ui", "**", "*.py"), recursive=True)
                 + glob.glob(os.path.join(_ROOT, "po_extractor", "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8-sig") as fh:
            tree = ast.parse(fh.read())
        module_level_t = any(
            isinstance(n, ast.ImportFrom)
            and any((a.asname or a.name) == "t" for a in n.names)
            for n in tree.body                      # top level only
        )
        if not module_level_t:
            continue
        top_level_imports = {id(n) for n in tree.body}
        local_bare_t_import = any(
            isinstance(n, ast.ImportFrom) and id(n) not in top_level_imports
            and any(a.name == "t" and a.asname is None for a in n.names)
            for n in ast.walk(tree)
        )
        if local_bare_t_import:
            offenders.append(os.path.relpath(path, _ROOT))
    assert not offenders, (
        f"modules re-import t() locally despite already having it at module "
        f"scope -- delete the redundant local import: {offenders}")


# ── Cold-import guard for circular imports ──────────────────────────────────

def _tab_entry_modules():
    """The view modules app.py imports lazily inside its tab functions.

    Those imports run only when a tab is opened, so nothing else in the suite
    reaches them — which is exactly why they need their own guard.
    """
    import re
    with open(_APP, encoding="utf-8") as fh:
        src = fh.read()
    return sorted(set(re.findall(r"^\s+from (ui\.[\w.]+) import", src, re.M)))


# Runs in a child interpreter. MODULES / PAIRS / ROOT are prepended by the
# test; the result is one JSON line of failure descriptions.
_CHILD = """
import importlib, json, sys
sys.path.insert(0, ROOT)


def purge():
    for name in [n for n in sys.modules
                 if n in ("ui", "po_extractor")
                 or n.startswith(("ui.", "po_extractor."))]:
        del sys.modules[name]


failures = []
for name in MODULES:
    purge()                 # must load as the FIRST project import
    try:
        importlib.import_module(name)
    except Exception as exc:
        failures.append("{}: {}: {}".format(name, type(exc).__name__, exc))

for first, second in PAIRS:
    purge()
    try:
        importlib.import_module(first)
        importlib.import_module(second)
    except Exception as exc:
        failures.append("{} then {}: {}: {}".format(
            first, second, type(exc).__name__, exc))

print(json.dumps(failures))
"""


def test_every_tab_module_imports_from_cold():
    """Each tab's module must import when it is the first thing loaded — what
    happens when a user opens that tab first.

    A circular import only fails for whichever side loads first, so once the
    suite has pulled the packages in a working order the cycle is invisible.
    That is how a release shipped which passed the entire suite and could not
    open its own first tab: ui_helpers.excel_reports imported
    exporters._excel_helpers at module scope, while exporters/__init__ imports
    back into ui_helpers.excel_reports.

    Deliberately run in a SUBPROCESS. Detecting this means emptying
    sys.modules, and doing that in-process leaves the rest of the suite holding
    stale module objects — twelve unrelated tests failed the first time this
    was written that way.
    """
    import json
    import subprocess
    import sys

    modules = _tab_entry_modules()
    assert modules, "no lazy 'from ui.x import' found in app.py — parser broken"

    # These two packages import each other; whichever loads first must work.
    pairs = [("po_extractor.ui_helpers.excel_reports", "po_extractor.exporters"),
             ("po_extractor.exporters", "po_extractor.ui_helpers.excel_reports")]

    preamble = "ROOT = %r\nMODULES = %r\nPAIRS = %r\n" % (_ROOT, modules, pairs)
    proc = subprocess.run([sys.executable, "-c", preamble + _CHILD],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, (
        "cold-import child failed:\n" + proc.stdout + "\n" + proc.stderr)

    failures = json.loads(proc.stdout.strip().splitlines()[-1])
    assert not failures, ("these fail when imported first (circular import?):"
                          "\n  " + "\n  ".join(failures))
