# hao npm Package

Category: `session-log`

Tags: `hao`, `cli`, `npm`, `packaging`, `agent-cli`

## Summary

`hao` is now installable as an npm package from `services/api-server`.
The package name is `@harness/hao` and it exposes the global command:

```text
hao -> bin/hao.cjs
```

The npm package does not reimplement the CLI in Node. It is a lightweight
launcher for the existing Python implementation:

```text
uv run --project <package-root> hao ...
```

## Files

```text
services/api-server/package.json
services/api-server/bin/hao.cjs
services/api-server/test/hao-launcher.test.cjs
services/api-server/app/cli/hao/config.py
services/api-server/app/cli/hao/main.py
services/api-server/tests/test_hao_cli.py
services/api-server/tests/test_hao_cli_v2.py
services/api-server/README.md
docs/cli/hao.md
```

## Behavior

- `npm install -g /path/to/harness/services/api-server` installs a global `hao`.
- After publish, `npm install -g @harness/hao` should install the same bin.
- `hao --version` prints the package version from the Python CLI entrypoint, so the npm wrapper and repo-installed CLI stay aligned.
- `hao -v`, `hao -V`, `hao --version`, and `hao version` now print the same version string.
- `hao login --api-url ... --token ...`, `hao status`, and `hao logout` are top-level aliases for common auth operations.
- `hao logout` clears only the persisted token in `config.toml`, keeps the saved API URL, preserves environment-variable override behavior, and does not remove `hao.db` or `sessions/`.
- `chat`, `plan`, and `act` accept shared run flags after the subcommand, so documented forms such as `hao plan --cwd /path "goal"` parse correctly.
- The launcher preserves the caller working directory so `hao --cwd .` still points at the user's workspace, not the installed package directory.
- `HAO_UV_BIN` can point at a non-PATH `uv` binary.
- `HAO_PYTHON_PROJECT` can override the bundled Python project during development.
- Missing `uv` and missing bundled `pyproject.toml` fail with actionable messages; missing project also exits non-zero.
- The package file list is restricted to `package.json`, `app/cli/hao` Python source, minimal `app` package markers, `pyproject.toml`, `uv.lock`, `README.md`, and the launcher; `__pycache__` files are not packed.
- The previous local global `hao@0.2.9` package conflict has been removed; `/Users/luohao/.nvm/versions/node/v24.15.0/bin/hao` now points to `../lib/node_modules/@harness/hao/bin/hao.cjs`, whose real path resolves to this workspace.

## Validation

```text
cd services/api-server && npm test
cd services/api-server && node --check bin/hao.cjs
cd services/api-server && node bin/hao.cjs --help
cd services/api-server && node bin/hao.cjs --version
cd services/api-server && uv run pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q -k 'version or login or logout or config'
cd services/api-server && uv run pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -q
cd services/api-server && uv run ruff check app/cli/hao/main.py app/cli/hao/config.py tests/test_hao_cli.py tests/test_hao_cli_v2.py
cd services/api-server && HAO_HOME=<tmp> uv run hao -v / version / login / status / logout smoke
cd services/api-server && node bin/hao.cjs plan --cwd /tmp "draft a plan" --help
cd services/api-server && HAO_PYTHON_PROJECT=/tmp/hao-definitely-missing-project node bin/hao.cjs --help # exits 1
cd services/api-server && npm pack --json --dry-run
cd services/api-server && npm pack && npm install -g --prefix <tmp> ./harness-hao-0.1.0.tgz && <tmp>/bin/hao --help
npm uninstall -g hao
npm install -g /Users/luohao/Desktop/agent_workspace/harness/services/api-server
command -v hao
npm ls -g --depth=0 @harness/hao
npm ls -g --depth=0 hao # exits 1, old same-name package absent
hao -v / -V / version / login / status / logout smoke
HAO_HOME=<tmp> hao # stays running as the installed TUI entrypoint before controlled kill
python3 scripts/validate-docs.py
git diff --check
```

Observed package smoke:

```text
Using CPython 3.11.15
Creating virtual environment at: <tmp>/lib/node_modules/@harness/hao/.venv
Installed 72 packages
<tmp>/bin/hao --help printed the expected hao CLI usage
```

Observed failure-path smoke:

```text
HAO_PYTHON_PROJECT=/tmp/hao-definitely-missing-project node bin/hao.cjs --help
rc=1
```

Observed local global install smoke:

```text
command -v hao
/Users/luohao/.nvm/versions/node/v24.15.0/bin/hao

ls -l /Users/luohao/.nvm/versions/node/v24.15.0/bin/hao
hao -> ../lib/node_modules/@harness/hao/bin/hao.cjs

realpath
/Users/luohao/Desktop/agent_workspace/harness/services/api-server/bin/hao.cjs

hao -v
hao 0.1.0

hao version
hao 0.1.0

HAO_HOME=<tmp> hao login/status/logout
config.toml keeps url = 'http://127.0.0.1:8000' and clears token = ''

HAO_HOME=<tmp> hao
hao_start_smoke_running=True
```

## Notes

The npm package still requires `uv`. This keeps the npm layer small and lets
the existing Python project own dependency resolution through `uv.lock`.
