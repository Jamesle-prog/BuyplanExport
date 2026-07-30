"""User management — bcrypt-hashed passwords + role + company assignments."""
from __future__ import annotations

import json
import os

# NOTE: bcrypt is imported lazily (see _bcrypt()) — it's a compiled extension
# that costs ~150 ms to import, and its hash routine another ~100 ms per call
# by design. Nothing before login needs it, but this module is pulled in at
# the very top of app.py, so an eager ``import bcrypt`` (plus the module-level
# dummy-hash that used to live here) put a quarter-second on every cold start
# and on the login page. It is loaded the first time a password is actually
# hashed or checked.

_USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")

_bcrypt_mod = None            # cached bcrypt module (populated on first use)
_dummy_hash: bytes | None = None   # timing-pad hash, computed once on demand


def _bcrypt():
    """Import bcrypt on first use and cache it on the module."""
    global _bcrypt_mod
    if _bcrypt_mod is None:
        import bcrypt
        _bcrypt_mod = bcrypt
    return _bcrypt_mod


def _timing_pad_hash() -> bytes:
    """A throwaway hash used to equalise ``verify_password`` timing when the
    username doesn't exist — an instant return would let an attacker tell
    valid usernames from invalid ones by response time. Computed lazily so a
    full bcrypt hash never runs at import."""
    global _dummy_hash
    if _dummy_hash is None:
        b = _bcrypt()
        _dummy_hash = b.hashpw(b"__timing_pad__", b.gensalt())
    return _dummy_hash

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
MODULE_EMAIL            = "email"              # inbox review + notifications
MODULE_RELEASES         = "releases"
# Cutting plans (裁剪计划). Deliberately its own module and NOT implied by any
# Sky East module: cut plans expose marker efficiency, fabric consumption and
# material cost, which the Buy Plan users must not see. Grant it explicitly.
MODULE_CUTTING_PLAN     = "cutting_plan"
# Settlement statistics (结算统计表). Its own module for the same reason as
# cut plans, only more so: these rows carry factory cost, margin and money
# received. Grant it explicitly.
MODULE_SETTLEMENT       = "settlement"
# Actual fabric condition (面料情况) -- shop-floor width/weight/shrinkage
# test log. Own module for the same reason as the others: a distinct data
# set with its own audience, granted explicitly rather than implied.
MODULE_FABRIC_CONDITION = "fabric_condition"

ALL_MODULES = [
    MODULE_GIII, MODULE_SKY_EAST, MODULE_SKY_EAST_BUYPLAN, MODULE_FABRIC_DB,
    MODULE_REFERENCE_DATA, MODULE_COLORS, MODULE_SUMMARY, MODULE_TRACKING,
    MODULE_CMPT, MODULE_EMAIL, MODULE_CUTTING_PLAN, MODULE_SETTLEMENT,
    MODULE_FABRIC_CONDITION, MODULE_RELEASES,
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
    MODULE_EMAIL: "📧 Email",
    MODULE_CUTTING_PLAN: "✂️ Cutting Plan",
    MODULE_SETTLEMENT: "💰 Settlement",
    MODULE_FABRIC_CONDITION: "📏 Fabric Condition",
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
                modules: list[str] | None = None,
                factories: list[str] | None = None) -> None:
    if not username or not password:
        raise ValueError("Username and password are required")
    users = _load()
    b = _bcrypt()
    hashed = b.hashpw(password.encode(), b.gensalt()).decode()
    existing = users.get(username, {})
    users[username] = {
        "password": hashed,
        "role": role if role is not None else existing.get("role", ROLE_USER),
        "companies": companies if companies is not None else existing.get("companies", []),
        "email": (email if email is not None else existing.get("email", "")) or "",
        "modules": modules if modules is not None else existing.get("modules", []),
        # Factory scope (production tracking): empty = not factory-restricted.
        # Preserved across edits that don't touch it (e.g. password change).
        "factories": factories if factories is not None else existing.get("factories", []),
    }
    _save(users)


def verify_password(username: str, password: str) -> bool:
    if not username or not password:
        return False
    b = _bcrypt()
    users = _load()
    rec = users.get(username)
    if not rec:
        # Spend the same time as a real check so a missing username can't be
        # distinguished from a wrong password by response time.
        b.checkpw(password.encode(), _timing_pad_hash())
        return False
    try:
        h = rec["password"] if isinstance(rec, dict) else rec
        return b.checkpw(password.encode(), h.encode())
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
                modules=rec.get("modules", []),
                factories=rec.get("factories", []))
    return True


# ------------------------------------------------------------------ #
# User info                                                            #
# ------------------------------------------------------------------ #

def list_users() -> list[str]:
    return list(_load().keys())


def get_user(username: str) -> dict | None:
    """Return {role, companies, email, modules, factories} or None."""
    rec = _load().get(username)
    if not rec:
        return None
    return {"role": rec.get("role", ROLE_USER),
            "companies": rec.get("companies", []),
            "email": rec.get("email", "") or "",
            "modules": rec.get("modules", []) or [],
            "factories": rec.get("factories", []) or []}


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


def get_user_factories(username: str) -> list[str]:
    """Factory scope for production tracking. Admin returns [] (unrestricted);
    a regular user with a non-empty list is restricted to those factories and
    may only record progress against them. Empty = not factory-restricted."""
    u = get_user(username)
    if not u:
        return []
    if u["role"] == ROLE_ADMIN:
        return []
    return u["factories"]


def set_user_factories(username: str, factories: list[str]) -> bool:
    users = _load()
    if username not in users:
        return False
    users[username]["factories"] = factories
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
