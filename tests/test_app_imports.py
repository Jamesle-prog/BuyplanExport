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


def _import_bound_names(node) -> set:
    """The names one import statement binds in its scope.

    ``import a.b`` binds "a"; ``import a.b as c`` binds "c";
    ``from m import x`` binds "x"; ``from m import x as y`` binds "y".
    ``from __future__ import ...`` and ``from m import *`` bind nothing we
    track.
    """
    out: set = set()
    if isinstance(node, ast.Import):
        for a in node.names:
            out.add(a.asname or a.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
        for a in node.names:
            if a.name != "*":
                out.add(a.asname or a.name)
    return out


def test_no_function_import_shadows_a_module_level_import():
    """A function-local import must never re-bind a name the file already
    imports at module level -- for ANY name, not just one.

    Assigning (or importing) a name ANYWHERE in a function body makes Python
    treat it as local for the WHOLE function, so a redundant local import
    doesn't just do nothing extra: it turns every earlier read of that name
    in the same function into a read of a not-yet-bound local, raising
    UnboundLocalError at runtime on whatever path reaches it first.

    This is exactly how v2.132.0..v2.137.0 shipped with every Sky East
    upload broken: ui/sky_east/processing.py's outer except block carried a
    local `from ui.i18n import t` that was CORRECT when written (the file
    had no module-level t then, v2.103.0) -- until the v2.132.0 i18n sweep
    added the module-level import and t(...) calls to the same function,
    leaving the old local import behind. The first t() read then crashed
    every run. The guard that existed at the time checked only "is t bound
    anywhere in the file", which the buggy local import satisfied; the first
    replacement guard was hardcoded to the name `t` and missed 17 more
    latent sites with the identical shape. Hence this general form.

    Deliberately does not try to prove a specific local import safe by
    checking whether it comes textually before or after each read --
    control flow (if/else, try/except: exactly the shape that hid the bug)
    makes that unreliable to determine statically. The rule is outright:

    - same source module as the module-level import -> DELETE the local
      import (the module-level binding is the identical object);
    - different source -> RENAME it (``from x import y as _y``) so no
      collision exists.

    Scope details, each load-bearing:
    - the module-level set is built from imports DIRECTLY in tree.body, so
      module-scope try/except import fallbacks (po_extractor/utils/
      image_extractor.py's defusedxml dance) and `if TYPE_CHECKING:` blocks
      are not counted as module bindings -- a runtime-absent TYPE_CHECKING
      name may legitimately be imported locally;
    - offenders are imports at ANY depth inside a function, including its
      own try/except/if -- again, the shape that hid the original bug;
    - matching is asname-or-name on BOTH sides, so `from m import x as y`
      colliding with a module-level `y` is caught too;
    - a file with no module-level import of the name is unaffected (see
      ui/memory.py: no top-level t import, so its local one is the
      legitimate sole source).
    """
    import glob
    offenders = []
    for path in (glob.glob(os.path.join(_ROOT, "ui", "**", "*.py"), recursive=True)
                 + glob.glob(os.path.join(_ROOT, "po_extractor", "**", "*.py"), recursive=True)):
        with open(path, encoding="utf-8-sig") as fh:   # 13 files carry a BOM
            tree = ast.parse(fh.read())
        module_names: set = set()
        for n in tree.body:                     # DIRECT top-level statements only
            module_names |= _import_bound_names(n)
        if not module_names:
            continue
        rel = os.path.relpath(path, _ROOT)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(fn):
                if isinstance(n, (ast.Import, ast.ImportFrom)):
                    clash = _import_bound_names(n) & module_names
                    if clash:
                        offenders.append(f"{rel}:{n.lineno} re-binds {sorted(clash)}")
    assert not offenders, (
        "function-local imports shadow a module-level import -- importing a "
        "name ANYWHERE in a function makes it local to the WHOLE function, "
        "so every earlier read of it in that function raises "
        "UnboundLocalError.\n"
        "Same source as the module-level import: DELETE the local import.\n"
        "Different source: RENAME it (from x import y as _y):\n  "
        + "\n  ".join(sorted(set(offenders))))


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
