from __future__ import annotations

import argparse
import getpass

from app.bootstrap.first_admin import create_admin_user
from app.db.session import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Harness owner admin user.")
    parser.add_argument("--email", help="Admin email address")
    parser.add_argument("--password", help="Admin password; omit to enter securely")
    parser.add_argument("--name", help="Display name")
    parser.add_argument(
        "--organization-name",
        default="Default Workspace",
        help="Initial organization name",
    )
    args = parser.parse_args(argv)

    email = (args.email or input("Admin email: ")).strip()
    password = args.password or getpass.getpass("Admin password: ")
    with SessionLocal() as session:
        user = create_admin_user(
            session,
            email=email,
            password=password,
            name=args.name,
            organization_name=args.organization_name,
        )
    print(f"created admin {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
