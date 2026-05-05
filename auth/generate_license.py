"""Generate a license.key for the current machine.

Usage (run from the project root)::

    python -m auth.generate_license

Writes ``auth/license.key`` and prints the machine ID to stdout.
Copy the resulting license.key alongside the app before distributing.
"""
from auth.license import _machine_id, _write_key, _LICENSE_KEY_PATH


def main() -> None:
    mid = _machine_id()
    _write_key(_LICENSE_KEY_PATH, mid)
    print(f"Machine ID : {mid}")
    print(f"License key written to: {_LICENSE_KEY_PATH}")


if __name__ == "__main__":
    main()
