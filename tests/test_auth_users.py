"""Tests for auth/users.py module-permission (tabs) feature."""
from __future__ import annotations

import auth.users as users


def test_create_user_defaults_modules_to_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    users.create_user("alice", "pw", role=users.ROLE_USER)
    info = users.get_user("alice")
    assert info["modules"] == []
    assert users.get_user_modules("alice") == []


def test_create_user_with_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    users.create_user(
        "buyplan_user", "pw", role=users.ROLE_USER,
        modules=[users.MODULE_SKY_EAST_BUYPLAN],
    )
    assert users.get_user_modules("buyplan_user") == [users.MODULE_SKY_EAST_BUYPLAN]


def test_admin_always_unrestricted_regardless_of_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    users.create_user(
        "admin1", "pw", role=users.ROLE_ADMIN,
        modules=[users.MODULE_SKY_EAST_BUYPLAN],
    )
    # Admins bypass module restrictions entirely — [] means unrestricted.
    assert users.get_user_modules("admin1") == []


def test_set_user_modules_updates_existing_user(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    users.create_user("bob", "pw", role=users.ROLE_USER)
    assert users.set_user_modules("bob", [users.MODULE_SKY_EAST_BUYPLAN]) is True
    assert users.get_user_modules("bob") == [users.MODULE_SKY_EAST_BUYPLAN]


def test_set_user_modules_missing_user_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    assert users.set_user_modules("nobody", [users.MODULE_GIII]) is False


def test_change_password_preserves_modules(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    users.create_user(
        "carol", "oldpw", role=users.ROLE_USER,
        modules=[users.MODULE_SKY_EAST_BUYPLAN],
    )
    assert users.change_password("carol", "oldpw", "newpw") is True
    assert users.get_user_modules("carol") == [users.MODULE_SKY_EAST_BUYPLAN]
    assert users.verify_password("carol", "newpw") is True


def test_all_modules_have_labels():
    for m in users.ALL_MODULES:
        assert m in users.MODULE_LABELS
