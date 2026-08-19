from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
from importlib import metadata
from pathlib import Path, PurePosixPath

from PyInstaller.__main__ import run as run_pyinstaller
from PyInstaller.archive.readers import CArchiveReader

from app.cli.harnessd import LOCAL_RUNTIME_ROUTER_MODULES
from app.db.sqlite_candidate_migration import create_fresh_sqlite_candidate

SERVICE_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = SERVICE_ROOT / "app" / "cli" / "harnessd.py"
MODEL_PRICING_SOURCES = SERVICE_ROOT / "app" / "settings" / "model_pricing_sources.json"
SOURCE_METADATA = SERVICE_ROOT / "agent_harness_api_server.egg-info"
LOCAL_RUNTIME_HIDDEN_IMPORTS = (
    "app.agents.subagent_timing",
    "app.runtime_jobs.handlers",
    "app.runtime_jobs.repository",
    "app.runtime_jobs.scheduler",
    "app.workers.actor_registration",
    "app.workers.agent_assignment_worker",
    "app.workers.alert_evaluator",
    "app.workers.subagent_recovery_worker",
    "app.workers.subagent_worker",
    "app.workers.team_runtime_worker",
)
EXCLUDED_MODULES = (
    "app.api.saml",
    "app.main",
    "app.security.saml_rate_limit",
    "app.workers.broker",
    "asyncpg",
    "dramatiq",
    "psycopg",
    "psycopg2",
    "redis",
)
FORBIDDEN_ARCHIVE_PREFIXES = ("asyncpg", "dramatiq", "psycopg", "psycopg2", "redis")
SQLITE_TEMPLATE_BUILD_PATH = SERVICE_ROOT / "build" / "harnessd-template" / "harness.sqlite3"


def _node_platform() -> str:
    if sys.platform == "darwin":
        return "darwin"
    if sys.platform == "win32":
        return "win32"
    if sys.platform.startswith("linux"):
        return "linux"
    raise RuntimeError(f"unsupported harnessd build platform: {sys.platform}")


def _node_architecture() -> str:
    architecture = platform.machine().lower()
    if architecture in {"x86_64", "amd64"}:
        return "x64"
    if architecture in {"arm64", "aarch64"}:
        return "arm64"
    raise RuntimeError(f"unsupported harnessd build architecture: {architecture}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the native harnessd sidecar.")
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=SERVICE_ROOT / "dist",
        help="parent directory for the harnessd artifact directory",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pyinstaller_options(
    dist_dir: Path,
    work_dir: Path,
    spec_dir: Path,
    sqlite_template: Path = SQLITE_TEMPLATE_BUILD_PATH,
) -> list[str]:
    data_separator = ":" if sys.platform != "win32" else ";"
    options = [
        str(ENTRYPOINT),
        "--name=harnessd",
        "--onedir",
        "--clean",
        "--noconfirm",
        f"--distpath={dist_dir}",
        f"--workpath={work_dir}",
        f"--specpath={spec_dir}",
        "--collect-all=uvicorn",
        f"--add-data={SERVICE_ROOT / 'alembic'}{data_separator}alembic",
        f"--add-data={SERVICE_ROOT / 'alembic.ini'}{data_separator}.",
        f"--add-data={MODEL_PRICING_SOURCES}{data_separator}app/settings",
        f"--add-data={sqlite_template}{data_separator}runtime-template",
    ]
    options.extend(
        f"--hidden-import={module_name}"
        for module_name, _prefix in LOCAL_RUNTIME_ROUTER_MODULES
    )
    options.extend(
        f"--hidden-import={module_name}" for module_name in LOCAL_RUNTIME_HIDDEN_IMPORTS
    )
    options.extend(f"--exclude-module={module_name}" for module_name in EXCLUDED_MODULES)
    if SOURCE_METADATA.is_dir():
        options.append(f"--add-data={SOURCE_METADATA}{data_separator}{SOURCE_METADATA.name}")
    else:
        options.append("--copy-metadata=agent-harness-api-server")
    return options


def _prepare_sqlite_template() -> tuple[Path, str]:
    template = SQLITE_TEMPLATE_BUILD_PATH
    template.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        (Path(f"{template}{suffix}")).unlink(missing_ok=True)
    revision = create_fresh_sqlite_candidate(template, alembic_ini=SERVICE_ROOT / "alembic.ini")
    return template, revision


def _archive_members(executable: Path) -> set[str]:
    archive = CArchiveReader(str(executable))
    members = set(archive.toc)
    for name, entry in archive.toc.items():
        if entry[-1] == "z":
            members.update(archive.open_embedded_archive(name).toc)
    return members


def _audit_archive(executable: Path) -> None:
    members = _archive_members(executable)
    forbidden_external = sorted(
        member
        for member in members
        if member.split(".", 1)[0].split("/", 1)[0] in FORBIDDEN_ARCHIVE_PREFIXES
    )
    if forbidden_external:
        sample = ", ".join(forbidden_external[:20])
        raise RuntimeError(f"harnessd archive contains server-only dependencies: {sample}")
    forbidden_app = sorted(
        member
        for member in members
        if any(
            member == excluded or member.startswith(f"{excluded}.")
            for excluded in EXCLUDED_MODULES
            if excluded.startswith("app.")
        )
    )
    if forbidden_app:
        sample = ", ".join(forbidden_app[:20])
        raise RuntimeError(f"harnessd archive contains excluded server modules: {sample}")


def _bundle_hashes(bundle_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(bundle_root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"harnessd bundle contains a symlink: {path}")
        if path.is_file():
            normalized_parts = {part.lower().split(".", 1)[0] for part in path.parts}
            if normalized_parts.intersection(FORBIDDEN_ARCHIVE_PREFIXES):
                raise RuntimeError(f"harnessd bundle contains a server-only dependency: {path}")
            hashes[path.relative_to(bundle_root).as_posix()] = _sha256(path)
    return hashes


def main() -> int:
    args = _parse_args()
    sqlite_template, template_revision = _prepare_sqlite_template()
    dist_dir = args.dist_dir.resolve() / "runtime" / _node_platform() / _node_architecture()
    work_dir = SERVICE_ROOT / "build" / "harnessd"
    spec_dir = SERVICE_ROOT / "build"
    executable_name = "harnessd.exe" if sys.platform == "win32" else "harnessd"
    if dist_dir.is_dir():
        shutil.rmtree(dist_dir)
    elif dist_dir.exists():
        dist_dir.unlink()
    dist_dir.mkdir(parents=True)
    bundle_dir = dist_dir / "harnessd"
    executable = bundle_dir / executable_name

    run_pyinstaller(_pyinstaller_options(dist_dir, work_dir, spec_dir, sqlite_template))

    if not executable.is_file():
        raise FileNotFoundError(f"PyInstaller did not create {executable}")
    _audit_archive(executable)
    files = _bundle_hashes(bundle_dir)
    template_matches = [
        relative_path
        for relative_path in files
        if PurePosixPath(relative_path).parts[-2:] == (
            "runtime-template",
            "harness.sqlite3",
        )
    ]
    if len(template_matches) != 1:
        raise RuntimeError(f"expected one packaged SQLite template, found {template_matches!r}")
    template_relative_path = f"harnessd/{template_matches[0]}"
    executable_relative = executable.relative_to(dist_dir).as_posix()
    manifest = {
        "schema_version": 2,
        "runtime_version": metadata.version("agent-harness-api-server"),
        "platform": _node_platform(),
        "architecture": _node_architecture(),
        "executable": executable_relative,
        "sha256": _sha256(executable),
        "sqlite_template": {
            "path": template_relative_path,
            "revision": template_revision,
            "sha256": files[template_matches[0]],
        },
        "files": {
            f"harnessd/{relative_path}": digest for relative_path, digest in files.items()
        },
    }
    (dist_dir / "runtime-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(dist_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
