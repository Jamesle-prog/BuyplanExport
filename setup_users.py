"""One-time script to create user accounts for the PO Extractor app.

Run once before first use:
    python setup_users.py

Re-run any time to add or reset a user. Existing users are overwritten
if you enter the same username again. The very first account created on
a fresh install (no users.json yet) is automatically made an admin, since
otherwise there's no way to bootstrap admin access on a new install without
hand-editing auth/users.json.
"""
import getpass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth.users import create_user, list_users, ROLE_ADMIN, ROLE_USER

BANNER = """
╔══════════════════════════════════════╗
║     PO Extractor — User Setup        ║
╚══════════════════════════════════════╝
"""


def prompt_user() -> tuple[str, str] | None:
    username = input("  Username (blank to finish): ").strip()
    if not username:
        return None
    while True:
        pw1 = getpass.getpass(f"  Password for '{username}': ")
        pw2 = getpass.getpass(f"  Confirm password: ")
        if not pw1:
            print("  ✗ Password cannot be empty. Try again.\n")
            continue
        if pw1 != pw2:
            print("  ✗ Passwords do not match. Try again.\n")
            continue
        return username, pw1


def role_for_slot(first_run: bool, created_so_far: int) -> str:
    """The very first account on a fresh install bootstraps as admin;
    every other slot (including later ones in the same run) is a regular user."""
    return ROLE_ADMIN if (first_run and created_so_far == 0) else ROLE_USER


def main():
    print(BANNER)
    first_run = not list_users()
    if first_run:
        print("No accounts exist yet — the first account you create will be an admin.\n")
    print("Create up to 3 user accounts (press Enter with no username to finish).\n")

    created = 0
    while created < 3:
        result = prompt_user()
        if result is None:
            break
        username, password = result
        role = role_for_slot(first_run, created)
        create_user(username, password, role=role)
        print(f"  ✓ User '{username}' saved{' as admin' if role == ROLE_ADMIN else ''}.\n")
        created += 1

    users = list_users()
    if users:
        print(f"Active accounts ({len(users)}): {', '.join(users)}")
    else:
        print("No users created. Run this script again before starting the app.")


if __name__ == "__main__":
    main()
