"""Pytest configuration: project root on sys.path, and a firewall between
the test suite and the live change log.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


@pytest.fixture(autouse=True)
def _change_log_never_touches_the_live_db(tmp_path_factory, monkeypatch):
    """Send any change-log write aimed at the LIVE database to a scratch one.

    Audit hooks write to the database of the store they belong to, so a test
    on a tmp_path is isolated by construction. Two things are not:

    * acts with no store to follow — creating a user, changing a role — which
      legitimately resolve the canonical database, and
    * tests that deliberately exercise the canonical factories
      (test_store_factories.py registers sentinel brands in the real
      boat_sample_req and deletes them again). Their cleanup removes the
      sentinel, but nothing removes the audit rows describing it.

    Together those filed 60 real rows into data/po_history.db before this
    fixture existed. Only the canonical path is redirected — every other
    path passes through untouched, so tests that assert on their own scratch
    change log still see exactly what they wrote.
    """
    from po_extractor.config import DB_PATH
    from po_extractor.store import change_log_store as cl_mod
    import po_extractor.store as store_pkg

    real = cl_mod.ChangeLogStore
    scratch = str(tmp_path_factory.mktemp("changelog") / "change_log.db")
    live = os.path.abspath(DB_PATH)

    class _RedirectedChangeLogStore(real):
        def __init__(self, db_path, *args, **kwargs):
            if os.path.abspath(str(db_path)) == live:
                db_path = scratch
            super().__init__(db_path, *args, **kwargs)

    monkeypatch.setattr(cl_mod, "ChangeLogStore", _RedirectedChangeLogStore)
    monkeypatch.setattr(store_pkg, "ChangeLogStore",
                        _RedirectedChangeLogStore, raising=False)
    monkeypatch.setattr(store_pkg, "get_change_log_store",
                        lambda: _RedirectedChangeLogStore(DB_PATH))
    yield


@pytest.fixture(autouse=True)
def _no_acting_user_leaks_between_tests():
    """Clear the thread-local acting user around every test.

    It is set per script run in the app and per test here; a value left behind
    would attribute one test's writes to another test's user, which is exactly
    the confusion the change log exists to remove.
    """
    from po_extractor.store.audit_context import clear_current_user
    clear_current_user()
    yield
    clear_current_user()
