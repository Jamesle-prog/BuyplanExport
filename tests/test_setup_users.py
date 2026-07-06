"""Tests for setup_users.py's first-run admin bootstrap logic."""
from __future__ import annotations

import setup_users
from auth.users import ROLE_ADMIN


def test_first_account_on_fresh_install_is_admin():
    assert setup_users.role_for_slot(first_run=True, created_so_far=0) == ROLE_ADMIN


def test_second_account_in_same_run_leaves_role_untouched():
    assert setup_users.role_for_slot(first_run=True, created_so_far=1) is None


def test_third_account_in_same_run_leaves_role_untouched():
    assert setup_users.role_for_slot(first_run=True, created_so_far=2) is None


def test_accounts_created_when_not_first_run_leave_role_untouched():
    assert setup_users.role_for_slot(first_run=False, created_so_far=0) is None
