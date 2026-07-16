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


def test_create_user_without_role_preserves_existing_admin_on_reset(tmp_path, monkeypatch):
    """Resetting an existing admin's password (e.g. via setup_users.py, which
    omits `role` for anyone but the very first bootstrap account) must not
    silently demote them back to a regular user."""
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    users.create_user("james", "oldpw", role=users.ROLE_ADMIN)
    users.create_user("james", "newpw")  # role omitted, as setup_users.py does
    info = users.get_user("james")
    assert info["role"] == users.ROLE_ADMIN
    assert users.verify_password("james", "newpw") is True


def test_create_user_without_role_defaults_brand_new_account_to_user(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    users.create_user("newperson", "pw")  # role omitted, no existing record
    assert users.get_user("newperson")["role"] == users.ROLE_USER


def test_create_user_with_explicit_role_still_overrides_existing(tmp_path, monkeypatch):
    monkeypatch.setattr(users, "_USERS_FILE", str(tmp_path / "users.json"))
    users.create_user("bob", "pw", role=users.ROLE_USER)
    users.create_user("bob", "pw2", role=users.ROLE_ADMIN)  # deliberate promotion
    assert users.get_user("bob")["role"] == users.ROLE_ADMIN


def test_corrupted_users_file_raises_clear_error_not_json_decode_error(tmp_path, monkeypatch):
    """A corrupted users.json (e.g. interrupted write) must fail loudly with
    a message pointing at the file, not raise a bare JSONDecodeError (which
    every caller would see as an unexplained crash) and must not silently
    return {} (which would make every login look like "wrong password" with
    no clue the real file is broken)."""
    users_file = tmp_path / "users.json"
    users_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(users, "_USERS_FILE", str(users_file))
    try:
        users._load()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "users.json" in str(e)
