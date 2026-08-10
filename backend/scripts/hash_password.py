"""Argon2id-Hash für AUTH_PASSWORD_HASH erzeugen (ADR 0005).

Aufruf aus `backend/`:

    uv run python scripts/hash_password.py

Das Passwort wird über getpass gelesen, erscheint also nicht in der
Shell-History. Ausgegeben wird nur der Hash — der gehört in die ENV des
API-Service, das Klartextpasswort nirgendwohin.
"""

import getpass
import sys

from argon2 import PasswordHasher


def main() -> int:
    passwort = getpass.getpass("Passwort: ")
    if not passwort:
        print("Abgebrochen: leeres Passwort.", file=sys.stderr)
        return 1
    if passwort != getpass.getpass("Wiederholen: "):
        print("Abgebrochen: Eingaben stimmen nicht ueberein.", file=sys.stderr)
        return 1

    print(PasswordHasher().hash(passwort))
    return 0


if __name__ == "__main__":
    sys.exit(main())
