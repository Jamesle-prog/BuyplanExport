"""Who may change a 船样要求.

The text is stored per (company, brand) and printed into the Sky East buy
plan, so a scoping mistake here doesn't just show one company another's data
— it lets one edit the other's output. The rule lives in one function so it
can be tested without a browser.
"""
from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="streamlit not installed in this test env")

import ui.boat_sample_view as v


@pytest.fixture
def companies(monkeypatch):
    """Three active companies, plus one deactivated."""
    monkeypatch.setattr(v, "list_company_names",
                        lambda active_only=True: ["Sky East", "GIII", "HHP"])
    return ["Sky East", "GIII", "HHP"]


def _as(monkeypatch, *, admin: bool, mine: list[str]):
    monkeypatch.setattr(v, "is_admin", lambda u: admin)
    monkeypatch.setattr(v, "get_user_companies", lambda u: mine)


def test_an_admin_may_edit_every_company(companies, monkeypatch):
    _as(monkeypatch, admin=True, mine=[])       # [] means unrestricted for admin
    assert v.editable_companies("boss") == companies


def test_a_user_may_edit_only_their_own(companies, monkeypatch):
    _as(monkeypatch, admin=False, mine=["GIII"])
    assert v.editable_companies("angel") == ["GIII"]


def test_a_user_assigned_to_several_gets_all_of_them(companies, monkeypatch):
    _as(monkeypatch, admin=False, mine=["HHP", "Sky East"])
    # Display order follows the company registry, not the user's list.
    assert v.editable_companies("angel") == ["Sky East", "HHP"]


def test_an_unassigned_user_may_edit_nothing(companies, monkeypatch):
    """The trap: get_user_companies returns [] both for an admin (meaning ALL)
    and for an unassigned regular user (meaning NONE). Reading it without the
    role check hands every company to an account entitled to none."""
    _as(monkeypatch, admin=False, mine=[])
    assert v.editable_companies("newbie") == []


def test_a_company_that_was_deactivated_drops_out(companies, monkeypatch):
    """Assignment alone isn't enough — the company must still be active."""
    _as(monkeypatch, admin=False, mine=["GIII", "Retired Ltd"])
    assert v.editable_companies("angel") == ["GIII"]


def test_the_admin_panel_and_the_user_section_share_one_editor():
    """If these ever diverge, one of the two mount points quietly stops
    getting fixes made to the other."""
    import ui.admin_boat_sample as admin
    assert admin.render_boat_sample_editor is v.render_boat_sample_editor


def test_the_two_mount_points_use_different_widget_keys():
    """Same editor, same session: a shared key would drag one panel's company
    selection into the other."""
    import inspect
    admin_src = inspect.getsource(__import__("ui.admin_boat_sample",
                                             fromlist=["x"]).show_boat_sample_admin)
    user_src = inspect.getsource(v.show_boat_sample_section)
    assert 'key_prefix="bsr_admin"' in admin_src
    assert 'key_prefix="bsr_ref"' in user_src
