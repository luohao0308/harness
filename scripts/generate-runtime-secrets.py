#!/usr/bin/env python3
"""Generate startup-level Harness runtime secrets.

The output is intended for `.env`, Docker Compose env files, Kubernetes
Secrets, or a deployment secret manager. Do not paste these values into the
Agent Console: they are platform startup secrets, not user/business secrets.
"""

from __future__ import annotations

import argparse
import base64
import secrets


def _fernet_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Harness startup secrets.")
    parser.add_argument(
        "--key-id",
        default="primary-v1",
        help="Identifier stored beside encrypted DB secrets for future rotation.",
    )
    args = parser.parse_args()
    print(f"AUTH_JWT_SECRET={secrets.token_hex(32)}")
    print(f"HARNESS_SECRET_ENCRYPTION_KEY={_fernet_key()}")
    print(f"HARNESS_SECRET_ENCRYPTION_KEY_ID={args.key_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
