"""One-time script to create the 4 standard login accounts for the PO
Extractor app: an unrestricted admin, plus one account each scoped to a
single module (Sky East, GIII, Fabric DB).

Run once before first use:
    python setup_users.py

Re-run any time to reset a password — existing accounts keep their role
and module scope; only the password changes (leave the password blank to
skip an account you don't want to touch this run). Usernames default to
the role name shown in [brackets]; press Enter to accept or type a
different one if you'd rather use a site-specific name. To change an
account's role/module scope later, use the admin panel's Users tab (or
call auth.users.set_user_modules / set_user_companies directly).
"""
import getpass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth.users import (
    create_user, get_user, list_users,
    ROLE_ADMIN, ROLE_USER,
    MODULE_SKY_EAST, MODULE_GIII, MODULE_FABRIC_DB,
)

BANNER = """
╔══════════════════════════════════════╗
║     PO Extractor — User Setup        ║
╚══════════════════════════════════════╝
"""

# (default_username, label, role, modules) — modules=[] means unrestricted
# (only ever appropriate for the admin slot; get_user_modules() also always
# returns [] for admins regardless of what's stored, per auth/users.py).
ACCOUNT_SLOTS = [
    ("admin",   "Admin (full access, all tabs)", ROLE_ADMIN, []),
    ("skyeast", "Sky East (Sky East tab only)",  ROLE_USER,  [MODULE_SKY_EAST]),
    ("giii",    "GIII (GIII tab only)",           ROLE_USER,  [MODULE_GIII]),
    ("fabric",  "Fabric DB (Fabric DB tab only)", ROLE_USER,  [MODULE_FABRIC_DB]),
]


def prompt_username(default: str) -> str:
    raw = input(f"  Username [{default}]: ").strip()
    return raw or default


def prompt_password(username: str) -> str | None:
    """Returns the new password, or None if the operator chose to skip
    this account (blank input at the first prompt)."""
    while True:
        pw1 = getpass.getpass(f"  Password for '{username}' (blank to skip): ")
        if not pw1:
            return None
        pw2 = getpass.getpass("  Confirm password: ")
        if pw1 != pw2:
            print("  ✗ Passwords do not match. Try again.\n")
            continue
        return pw1


def main():
    print(BANNER)
    existing = set(list_users())
    if existing:
        print(f"Existing accounts: {', '.join(sorted(existing))}")
        print("Re-entering a username below resets its password only — role and "
              "module scope are left as they already are.\n")
    else:
        print("No accounts exist yet. Creating the 4 standard accounts below.\n")

    for default_username, label, role, modules in ACCOUNT_SLOTS:
        print(f"-- {label} --")
        username = prompt_username(default_username)
        password = prompt_password(username)
        if password is None:
            print("  (skipped)\n")
            continue
        # Existing account: password reset ONLY -- role/modules stay exactly
        # as they are (create_user preserves them when passed None). Passing
        # the slot's role/modules here would silently clobber a custom scope,
        # or demote an admin whose username was typed into a user slot.
        already_exists = get_user(username) is not None
        create_user(
            username, password,
            role=None if already_exists else role,
            modules=None if already_exists else modules,
        )
        final = get_user(username)
        scope = "all tabs" if not final["modules"] else ", ".join(final["modules"])
        print(f"  ✓ User '{username}' saved (role: {final['role']}, modules: {scope}).\n")

    users = list_users()
    if users:
        print(f"Active accounts ({len(users)}): {', '.join(users)}")
    else:
        print("No users created. Run this script again before starting the app.")


if __name__ == "__main__":
    main()
