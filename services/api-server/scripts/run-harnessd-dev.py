from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch harnessd with an ephemeral dev bootstrap.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/local-runtime"))
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    payload = {
        "runtime_data_dir": str(args.data_dir.expanduser().resolve()),
        "session_signing_secret": secrets.token_urlsafe(48),
        "vault_encryption_secret": secrets.token_urlsafe(48),
        "desktop_bootstrap_token": secrets.token_urlsafe(48),
    }
    process = subprocess.run(
        [sys.executable, "-m", "app.cli.harnessd", "--port", str(args.port)],
        input=json.dumps(payload),
        text=True,
        check=False,
    )
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
