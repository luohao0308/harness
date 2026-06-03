#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "services/api-server"
sys.path.insert(0, str(API_DIR))

from app.cli.create_admin import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
