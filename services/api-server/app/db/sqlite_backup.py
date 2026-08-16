from __future__ import annotations

import sqlite3
from pathlib import Path

from app.db.sqlite_integrity import check_sqlite_integrity


def backup_sqlite_database(source: str | Path, destination: str | Path) -> Path:
    """Create a consistent SQLite backup, including committed WAL contents."""
    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if source_path == destination_path:
        raise ValueError("SQLite backup destination must differ from source")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        raise FileExistsError(destination_path)

    source_connection = sqlite3.connect(f"{source_path.as_uri()}?mode=ro", uri=True, timeout=5)
    destination_connection = sqlite3.connect(destination_path)
    try:
        source_connection.backup(destination_connection, pages=256, sleep=0.01)
    except BaseException:
        destination_connection.close()
        source_connection.close()
        destination_path.unlink(missing_ok=True)
        raise
    else:
        destination_connection.close()
        source_connection.close()
    check_sqlite_integrity(destination_path)
    return destination_path
