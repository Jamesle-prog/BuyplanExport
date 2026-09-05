"""Tests for auth.login_throttle.

The important one is the last: the throttle must survive Streamlit
re-executing app.py in a fresh namespace on every run.  The previous
inline implementation did not, and never locked anyone out.
"""
from __future__ import annotations

import ast
import os

import pytest

from auth import login_throttle as th


@pytest.fixture(autouse=True)
def _clean():
    th.reset()
    yield
    th.reset()


def test_below_threshold_is_not_locked():
    for _ in range(4):
        th.record_failure("alice", threshold=5)
    assert th.lock_remaining("alice") == 0
    assert th.wait_seconds("alice") == 0


def test_threshold_locks_for_base_period():
    for _ in range(5):
        th.record_failure("alice", threshold=5, base_lock_s=60, max_lock_s=900)
    assert 55 <= th.lock_remaining("alice") <= 61


def test_backoff_doubles_and_is_capped():
    for _ in range(5):
        th.record_failure("alice", threshold=5, base_lock_s=60, max_lock_s=900)
    first = th.lock_remaining("alice")
    th.record_failure("alice", threshold=5, base_lock_s=60, max_lock_s=900)
    second = th.lock_remaining("alice")
    assert second > first * 1.5            # 60 → 120
    for _ in range(10):
        th.record_failure("alice", threshold=5, base_lock_s=60, max_lock_s=900)
    assert th.lock_remaining("alice") <= 901   # capped, not 60 * 2**10


def test_success_clears_the_key():
    for _ in range(5):
        th.record_failure("alice", threshold=5)
    th.record_success("alice")
    assert th.wait_seconds("alice") == 0


def test_keys_are_independent():
    for _ in range(5):
        th.record_failure("alice", threshold=5)
    assert th.lock_remaining("alice") > 0
    assert th.lock_remaining("bob") == 0


def test_spraying_brake_is_per_source_address():
    """Spraying many usernames from one address trips that address's brake —
    even for a name that has never failed — but NOT other addresses: one
    colleague hammering a wrong password must not lock the whole team out."""
    for i in range(30):
        th.record_failure(f"user{i}")
        th.record_global_failure("10.0.0.5")
    assert th.wait_seconds("never-seen-before", "10.0.0.5") > 0
    assert th.wait_seconds("never-seen-before", "10.0.0.9") == 0


def test_unknown_source_falls_back_to_a_global_brake():
    for _ in range(30):
        th.record_global_failure("")          # no client address available
    assert th.wait_seconds("anyone", "") > 0
    assert th.wait_seconds("anyone", "10.0.0.9") == 0


def test_state_survives_a_fresh_script_namespace():
    """Model what Streamlit does: exec the *using* code into a brand-new
    module namespace on every run.  Counters kept in the imported module
    carry across; counters defined in the script would not."""
    script = (
        "from auth import login_throttle as th\n"
        "th.record_failure('carol', threshold=5)\n"
        "remaining = th.lock_remaining('carol')\n"
    )
    last = 0
    for _run in range(5):
        ns: dict = {}                    # fresh __main__ each time, like Streamlit
        exec(compile(script, "<app.py>", "exec"), ns)
        last = ns["remaining"]
    assert last > 0, "5 failures across 5 fresh namespaces must lock the key"


def test_app_py_keeps_no_throttle_state_at_module_level():
    """Regression guard for the original bug: any dict/set/list assigned at
    app.py's top level is recreated on every Streamlit run, so throttle
    state must never live there again."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "app.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    offenders = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                name = getattr(t, "id", "")
                if "LOGIN" in name.upper() and "FAIL" in name.upper():
                    offenders.append(name)
    assert not offenders, f"throttle state defined in app.py: {offenders}"
    # The throttle is used by the login page, which lives in ui/login_view.py.
    view = open(os.path.join(root, "ui", "login_view.py"), encoding="utf-8").read()
    assert "login_throttle" in view
