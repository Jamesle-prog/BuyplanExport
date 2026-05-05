"""One-time script to create user accounts for the PO Extractor app.

Run once before first use:
    python setup_users.py

Re-run any time to add or reset a user. Existing users are overwritten
if you enter the same username again.
"""
import getpass
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth.users import create_user, list_users

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


def main():
    print(BANNER)
    print("Create up to 3 user accounts (press Enter with no username to finish).\n")

    created = 0
    while created < 3:
        result = prompt_user()
        if result is None:
            break
        username, password = result
        create_user(username, password)
        print(f"  ✓ User '{username}' saved.\n")
        created += 1

    users = list_users()
    if users:
        print(f"Active accounts ({len(users)}): {', '.join(users)}")
    else:
        print("No users created. Run this script again before starting the app.")


if __name__ == "__main__":
    main()
