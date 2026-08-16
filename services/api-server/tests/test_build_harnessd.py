from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from app.cli.harnessd import LOCAL_RUNTIME_ROUTER_MODULES

SERVICE_ROOT = Path(__file__).resolve().parents[1]


def _build_module():
    path = SERVICE_ROOT / "scripts" / "build-harnessd.py"
    spec = importlib.util.spec_from_file_location("build_harnessd", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_uses_audited_local_allowlist_and_server_exclusions(tmp_path: Path) -> None:
    build = _build_module()
    options = build._pyinstaller_options(tmp_path / "dist", tmp_path / "work", tmp_path)

    assert "--onedir" in options
    assert "--onefile" not in options
    assert "--collect-submodules=app" not in options
    assert (
        f"--add-data={build.MODEL_PRICING_SOURCES}:app/settings" in options
        if sys.platform != "win32"
        else f"--add-data={build.MODEL_PRICING_SOURCES};app/settings" in options
    )
    assert (
        f"--add-data={build.SQLITE_TEMPLATE_BUILD_PATH}:runtime-template" in options
        if sys.platform != "win32"
        else f"--add-data={build.SQLITE_TEMPLATE_BUILD_PATH};runtime-template" in options
    )
    if build.SOURCE_METADATA.is_dir():
        assert any(
            option.startswith(f"--add-data={build.SOURCE_METADATA}")
            for option in options
        )
    else:
        assert "--copy-metadata=agent-harness-api-server" in options
    hidden_imports = {
        option.removeprefix("--hidden-import=")
        for option in options
        if option.startswith("--hidden-import=")
    }
    assert hidden_imports == {
        module_name for module_name, _prefix in LOCAL_RUNTIME_ROUTER_MODULES
    } | set(build.LOCAL_RUNTIME_HIDDEN_IMPORTS)
    exclusions = {
        option.removeprefix("--exclude-module=")
        for option in options
        if option.startswith("--exclude-module=")
    }
    assert {
        "app.main",
        "app.workers.broker",
        "redis",
        "dramatiq",
        "psycopg",
        "psycopg2",
        "asyncpg",
    } <= exclusions


def test_local_router_allowlist_does_not_import_server_drivers(tmp_path: Path) -> None:
    modules = repr([module_name for module_name, _prefix in LOCAL_RUNTIME_ROUTER_MODULES])
    code = f"""
import importlib
import sys
from pathlib import Path
from app.local_runtime.bootstrap import LocalRuntimeBootstrap

LocalRuntimeBootstrap(
    runtime_data_dir=Path({str(tmp_path)!r}),
    session_signing_secret="s" * 32,
    vault_encryption_secret="v" * 32,
    desktop_bootstrap_token="t" * 32,
).install()
for module_name in {modules}:
    importlib.import_module(module_name)
bad = sorted(
    module_name
    for module_name in sys.modules
    if module_name.split(".", 1)[0] in {{"redis", "dramatiq", "psycopg", "psycopg2", "asyncpg"}}
)
if bad:
    raise SystemExit("server-only modules imported: " + ", ".join(bad))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=SERVICE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_harnessd_entrypoint_does_not_import_server_app() -> None:
    source = (SERVICE_ROOT / "app" / "cli" / "harnessd.py").read_text(encoding="utf-8")
    assert "from app.main import app" not in source


def test_bundle_hashes_cover_files_and_reject_symlinks(tmp_path: Path) -> None:
    build = _build_module()
    bundle = tmp_path / "harnessd"
    bundle.mkdir()
    executable = bundle / "harnessd"
    executable.write_bytes(b"entry")
    resource = bundle / "_internal" / "resource.txt"
    resource.parent.mkdir()
    resource.write_bytes(b"resource")
    pricing_sources = bundle / "_internal" / "app" / "settings" / "model_pricing_sources.json"
    pricing_sources.parent.mkdir(parents=True)
    pricing_sources.write_bytes(b'{"schema_version":"model_pricing_sources.v1"}')

    hashes = build._bundle_hashes(bundle)

    assert hashes == {
        "_internal/app/settings/model_pricing_sources.json": build._sha256(pricing_sources),
        "_internal/resource.txt": build._sha256(resource),
        "harnessd": build._sha256(executable),
    }
    link = bundle / "linked-entry"
    link.symlink_to(executable)
    try:
        build._bundle_hashes(bundle)
    except RuntimeError as exc:
        assert "symlink" in str(exc)
    else:
        raise AssertionError("bundle symlink was accepted")


def test_bundle_hashes_reject_server_driver_paths(tmp_path: Path) -> None:
    build = _build_module()
    bundle = tmp_path / "harnessd"
    driver = bundle / "_internal" / "redis" / "client.pyc"
    driver.parent.mkdir(parents=True)
    driver.write_bytes(b"driver")

    try:
        build._bundle_hashes(bundle)
    except RuntimeError as exc:
        assert "server-only dependency" in str(exc)
    else:
        raise AssertionError("server-only bundle path was accepted")
