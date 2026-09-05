"""Password hashes use the configured work factor and upgrade on sign-in."""
from __future__ import annotations

import json

import pytest

from auth import users
from po_extractor.config import BCRYPT_ROUNDS


@pytest.fixture()
def users_file(tmp_path, monkeypatch):
    f = tmp_path / "users.json"
    monkeypatch.setattr(users, "_USERS_FILE", str(f))
    return f


def test_new_hashes_use_the_configured_rounds(users_file):
    users.create_user("amy", "pw", role="user", companies=["GIII"])
    h = json.loads(users_file.read_text())["amy"]["password"]
    assert users._hash_rounds(h) == BCRYPT_ROUNDS


def test_legacy_hash_still_verifies_and_is_upgraded_on_login(users_file):
    b = users._bcrypt()
    legacy = b.hashpw(b"pw", b.gensalt(rounds=BCRYPT_ROUNDS + 2)).decode()
    users_file.write_text(json.dumps({"amy": {
        "password": legacy, "role": "admin", "companies": ["GIII"],
        "modules": ["giii"], "factories": ["F1"], "email": "a@x"}}))

    assert users.verify_password("amy", "pw") is True

    rec = json.loads(users_file.read_text())["amy"]
    assert users._hash_rounds(rec["password"]) == BCRYPT_ROUNDS, "re-hashed"
    assert rec["role"] == "admin" and rec["companies"] == ["GIII"]
    assert rec["modules"] == ["giii"] and rec["factories"] == ["F1"]
    assert rec["email"] == "a@x"
    assert users.verify_password("amy", "pw") is True     # new hash works
    assert users.verify_password("amy", "nope") is False


def test_wrong_password_never_rewrites_the_hash(users_file):
    b = users._bcrypt()
    legacy = b.hashpw(b"pw", b.gensalt(rounds=BCRYPT_ROUNDS + 2)).decode()
    users_file.write_text(json.dumps({"amy": {"password": legacy, "role": "user"}}))
    assert users.verify_password("amy", "wrong") is False
    assert json.loads(users_file.read_text())["amy"]["password"] == legacy


def test_timing_pad_matches_the_configured_rounds(monkeypatch):
    monkeypatch.setattr(users, "_dummy_hash", None)
    assert users._hash_rounds(users._timing_pad_hash().decode()) == BCRYPT_ROUNDS
