"""User management — bcrypt-hashed passwords + role + company assignments."""
import json
import os

import bcrypt

_USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

# Roles
ROLE_ADMIN = "admin"
ROLE_USER  = "user"

# Modules — one per top-level app tab, plus a narrower sub-scope for Sky East.
# A user's `modules` list gates which tabs render for them; an empty list means
# unrestricted (all modules) — same convention as `companies`. Admins always
# get every module regardless of this field.
MODULE_GIII             = "giii"
MODULE_SKY_EAST         = "sky_east"           # full Sky East tab (Upload/Reports/History/Missing)
MODULE_SKY_EAST_BUYPLAN = "sky_east_buyplan"   # Sky East narrowed to Upload + Buy Plan generation only
MODULE_FABRIC_DB        = "fabric_db"
MODULE_REFERENCE_DATA   = "reference_data"
MODULE_COLORS           = "colors"
MODULE_SUMMARY          = "summary"
MODULE_TRACKING         = "tracking"
MODULE_CMPT             = "cmpt"               # CMPT (加工) contracts + price ledger
MODULE_RELEASES         = "releases"

ALL_MODULES = [
    MODULE_GIII, MODULE_SKY_EAST, MODULE_SKY_EAST_BUYPLAN, MODULE_FABRIC_DB,
    MODULE_REFERENCE_DATA, MODULE_COLORS, MODULE_SUMMARY, MODULE_TRACKING,
    MODULE_CMPT, MODULE_RELEASES,
]

MODULE_LABELS = {
    MODULE_GIII: "📋 GIII",
    MODULE_SKY_EAST: "🛍 Sky East (full)",
    MODULE_SKY_EAST_BUYPLAN: "🛍 Sky East — Buy Plan only",
    MODULE_FABRIC_DB: "🧵 Fabric DB",
    MODULE_REFERENCE_DATA: "📐 Reference Data",
    MODULE_COLORS: "🎨 Colors",
    MODULE_SUMMARY: "📊 Summary",
    MODULE_TRACKING: "🏭 Tracking",
    MODULE_CMPT: "📄 CMPT Contracts",
    MODULE_RELEASES: "🔖 Releases",
}


def _load() -> dict:
    if not os.path.exists(_USERS_FILE):
        return {}
    with open(_USERS_FILE, "r", encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            # Fail loudly rather than silently returning {} -- that would make
            # every login "wrong password" with no clue the real problem is a
            # corrupted users.json (e.g. an interrupted write).
            raise RuntimeError(
                f"{_USERS_FILE} is corrupted and could not be parsed as JSON: {e}. "
                "Restore it from a backup before logging in."
            ) from e
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
                role: str | None = None,
                companies: list[str] | None = None,
                email: str | None = None,
                modules: list[str] | None = None) -> None:
    if not username or not password:
        raise ValueError("Username and password are required")
    users = _load()
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    existing = users.get(username, {})
    users[username] = {
        "password": hashed,
        "role": role if role is not None else existing.get("role", ROLE_USER),
        "companies": companies if companies is not None else existing.get("companies", []),
        "email": (email if email is not None else existing.get("email", "")) or "",
        "modules": modules if modules is not None else existing.get("modules", []),
    }
    _save(users)


# Throwaway hash used to equalise timing when the username doesn't exist —
# an instant return let attackers distinguish valid usernames from invalid
# ones by response time (missing user ≈ instant; real user ≈ full bcrypt).
_DUMMY_HASH = bcrypt.hashpw(b"__timing_pad__", bcrypt.gensalt()).decode()


def verify_password(username: str, password: str) -> bool:
    if not username or not password:
        return False
    users = _load()
    rec = users.get(username)
    if not rec:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH.encode())
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
                companies=rec.get("companies", []),
                modules=rec.get("modules", []))
    return True


# ------------------------------------------------------------------ #
# User info                                                            #
# ------------------------------------------------------------------ #

def list_users() -> list[str]:
    return list(_load().keys())


def get_user(username: str) -> dict | None:
    """Return {role, companies, email, modules} or None."""
    rec = _load().get(username)
    if not rec:
        return None
    return {"role": rec.get("role", ROLE_USER),
            "companies": rec.get("companies", []),
            "email": rec.get("email", "") or "",
            "modules": rec.get("modules", []) or []}


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


def get_user_modules(username: str) -> list[str]:
    """Admin returns [] (meaning all). Regular user returns their list —
    empty also means unrestricted (same convention as get_user_companies)."""
    u = get_user(username)
    if not u:
        return []
    if u["role"] == ROLE_ADMIN:
        return []
    return u["modules"]


def set_user_modules(username: str, modules: list[str]) -> bool:
    users = _load()
    if username not in users:
        return False
    users[username]["modules"] = modules
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
