"""The login page lives in ui.login_view; app.py keeps only the router."""
from __future__ import annotations

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_login_view_exposes_the_page_and_the_password_form():
    import ui.login_view as lv
    assert callable(lv.show_login) and callable(lv.show_change_password_sidebar)
    assert "fonts" in lv._LOGIN_CSS   # the page CSS moved with it


def test_app_py_no_longer_defines_the_login_page():
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    names = {n.name for n in ast.parse(src).body
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for gone in ("show_login", "_login_hero_html", "_client_ip", "_record_login",
                 "_show_change_password_sidebar"):
        assert gone not in names, f"{gone} should live in ui/login_view.py"
    assert "_LOGIN_CSS" not in src
    assert "from ui.login_view import show_login" in src
