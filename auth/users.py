"""User management — bcrypt-hashed passwords + role + company assignments."""
import json
import os

import bcrypt

_USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

# Roles
ROLE_ADMIN = "admin"
ROLE_USER  = "user"


def _load() -> dict:
    if not os.path.exists(_USERS_FILE):
        return {}
    with open(_USERS_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    # Migrate flat {username: hash_str} → {username: {password, role, companies}}
    migrated = False
    for k, v in raw.items():
        if isinstance(v, str):
            raw[k] = {"password": v, "role": ROLE_ADMIN, "companies": []}
            migrated = True
    if migrated:
        _save(raw)
    return raw


def _save(users: dict) -> None:
    with open(_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


# ------------------------------------------------------------------ #
# Auth                                                                 #
# ------------------------------------------------------------------ #

def create_user(username: str, password: str,
                role: str = ROLE_USER,
                companies: list[str] | None = None,
                email: str | None = None) -> None:
    if not username or not password:
        raise ValueError("Username and password are required")
    users = _load()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    existing = users.get(username, {})
    users[username] = {
        "password": hashed,
        "role": role,
        "companies": companies if companies is not None else existing.get("companies", []),
        "email": (email if email is not None else existing.get("email", "")) or "",
    }
    _save(users)


def verify_password(username: str, password: str) -> bool:
    if not username or not password:
        return False
    users = _load()
    rec = users.get(username)
    if not rec:
        return False
    try:
        h = rec["password"] if isinstance(rec, dict) else rec
        return bcrypt.checkpw(password.encode(), h.encode())
    except Exception:
        return False


def change_password(username: str, old_password: str, new_password: str) -> bool:
    if not verify_password(username, old_password):
        return False
    users = _load()
    rec = users.get(username, {})
    create_user(username, new_password,
                role=rec.get("role", ROLE_USER),
                companies=rec.get("companies", []))
    return True


# ------------------------------------------------------------------ #
# User info                                                            #
# ------------------------------------------------------------------ #

def list_users() -> list[str]:
    return list(_load().keys())


def get_user(username: str) -> dict | None:
    """Return {role, companies, email} or None."""
    rec = _load().get(username)
    if not rec:
        return None
    return {"role": rec.get("role", ROLE_USER),
            "companies": rec.get("companies", []),
            "email": rec.get("email", "") or ""}


def get_user_email(username: str) -> str:
    """Return the user's email or empty string."""
    u = get_user(username)
    return (u or {}).get("email", "")


def set_user_email(username: str, email: str) -> bool:
    users = _load()
    if username not in users:
        return False
    users[username]["email"] = (email or "").strip()
    _save(users)
    return True


def is_admin(username: str) -> bool:
    u = get_user(username)
    return bool(u and u["role"] == ROLE_ADMIN)


def get_user_companies(username: str) -> list[str]:
    """Admin returns [] (meaning all). Regular user returns their list."""
    u = get_user(username)
    if not u:
        return []
    if u["role"] == ROLE_ADMIN:
        return []   # empty = unrestricted
    return u["companies"]


def set_user_companies(username: str, companies: list[str]) -> bool:
    users = _load()
    if username not in users:
        return False
    users[username]["companies"] = companies
    _save(users)
    return True


def set_user_role(username: str, role: str) -> bool:
    users = _load()
    if username not in users:
        return False
    users[username]["role"] = role
    _save(users)
    return True


def delete_user(username: str) -> bool:
    users = _load()
    if username not in users:
        return False
    del users[username]
    _save(users)
    return True


def user_exists() -> bool:
    return bool(_load())
