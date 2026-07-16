"""Tests for setup_users.py's 4 fixed role-scoped account slots."""
from __future__ import annotations

import builtins

import setup_users
import auth.users as users_mod
from auth.users import ROLE_ADMIN, ROLE_USER, MODULE_SKY_EAST, MODULE_GIII, MODULE_FABRIC_DB


def test_account_slots_has_exactly_four_entries():
    assert len(setup_users.ACCOUNT_SLOTS) == 4


def test_account_slots_covers_admin_skyeast_giii_fabric():
    defaults = [slot[0] for slot in setup_users.ACCOUNT_SLOTS]
    assert defaults == ["admin", "skyeast", "giii", "fabric"]


def test_admin_slot_is_role_admin_and_unrestricted():
    _, _, role, modules = setup_users.ACCOUNT_SLOTS[0]
    assert role == ROLE_ADMIN
    assert modules == []


def test_skyeast_giii_fabric_slots_are_role_user_single_module():
    by_default = {slot[0]: slot for slot in setup_users.ACCOUNT_SLOTS}
    assert by_default["skyeast"][2] == ROLE_USER
    assert by_default["skyeast"][3] == [MODULE_SKY_EAST]
    assert by_default["giii"][2] == ROLE_USER
    assert by_default["giii"][3] == [MODULE_GIII]
    assert by_default["fabric"][2] == ROLE_USER
    assert by_default["fabric"][3] == [MODULE_FABRIC_DB]


def test_prompt_username_blank_uses_default(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *_a: "")
    assert setup_users.prompt_username("admin") == "admin"


def test_prompt_username_override(monkeypatch):
    monkeypatch.setattr(builtins, "input", lambda *_a: "boss")
    assert setup_users.prompt_username("admin") == "boss"


def test_prompt_password_blank_skips(monkeypatch):
    monkeypatch.setattr(setup_users.getpass, "getpass", lambda *_a: "")
    assert setup_users.prompt_password("admin") is None


def test_prompt_password_mismatch_then_match(monkeypatch):
    calls = iter(["pw1", "different", "pw1", "pw1"])
    monkeypatch.setattr(setup_users.getpass, "getpass", lambda *_a: next(calls))
    assert setup_users.prompt_password("admin") == "pw1"


def test_main_creates_all_four_accounts_with_correct_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(users_mod, "_USERS_FILE", str(tmp_path / "users.json"))

    usernames = iter(["", "", "", ""])   # accept every default username
    monkeypatch.setattr(builtins, "input", lambda *_a: next(usernames))

    passwords = iter([
        "adminpw", "adminpw",
        "skyeastpw", "skyeastpw",
        "giiipw", "giiipw",
        "fabricpw", "fabricpw",
    ])
    monkeypatch.setattr(setup_users.getpass, "getpass", lambda *_a: next(passwords))

    setup_users.main()

    assert set(users_mod.list_users()) == {"admin", "skyeast", "giii", "fabric"}
    assert users_mod.get_user("admin")["role"] == ROLE_ADMIN
    assert users_mod.get_user("skyeast")["role"] == ROLE_USER
    assert users_mod.get_user("skyeast")["modules"] == [MODULE_SKY_EAST]
    assert users_mod.get_user("giii")["modules"] == [MODULE_GIII]
    assert users_mod.get_user("fabric")["modules"] == [MODULE_FABRIC_DB]
    assert users_mod.verify_password("admin", "adminpw")


def test_main_skipping_an_account_leaves_it_unset(tmp_path, monkeypatch):
    """Blank password at the first prompt for a slot must not create that
    account at all -- e.g. a site that doesn't need a Fabric DB user."""
    monkeypatch.setattr(users_mod, "_USERS_FILE", str(tmp_path / "users.json"))

    usernames = iter(["", "", "", ""])
    monkeypatch.setattr(builtins, "input", lambda *_a: next(usernames))

    passwords = iter([
        "adminpw", "adminpw",
        "skyeastpw", "skyeastpw",
        "",              # giii: blank -> skip
        "",              # fabric: blank -> skip
    ])
    monkeypatch.setattr(setup_users.getpass, "getpass", lambda *_a: next(passwords))

    setup_users.main()

    assert set(users_mod.list_users()) == {"admin", "skyeast"}


def test_rerunning_resets_password_but_preserves_role(tmp_path, monkeypatch):
    monkeypatch.setattr(users_mod, "_USERS_FILE", str(tmp_path / "users.json"))
    users_mod.create_user("skyeast", "oldpw", role=ROLE_USER, modules=[MODULE_SKY_EAST])

    usernames = iter(["", "", "", ""])
    monkeypatch.setattr(builtins, "input", lambda *_a: next(usernames))
    # 1 getpass call per skipped slot (admin, giii, fabric), 2 for skyeast's
    # actual reset (new password + confirmation).
    passwords = iter(["", "newpw", "newpw", "", ""])
    monkeypatch.setattr(setup_users.getpass, "getpass", lambda *_a: next(passwords))

    setup_users.main()

    assert users_mod.verify_password("skyeast", "newpw")
    assert users_mod.get_user("skyeast")["role"] == ROLE_USER
    assert users_mod.get_user("skyeast")["modules"] == [MODULE_SKY_EAST]
