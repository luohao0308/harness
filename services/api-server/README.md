# hao npm package

This directory can be installed as the npm package `@harness/hao`.
It exposes the `hao` command and launches the existing Python CLI through
`uv run --project <package-root> hao ...`.

## Requirements

- Node.js 18 or newer.
- `uv` available on `PATH`.

Install `uv` from <https://docs.astral.sh/uv/getting-started/installation/>.

If `hao --help` shows `install / uninstall / list / version`, you are still
running the old global `hao` package. Remove it first:

```bash
npm uninstall -g hao
npm install -g /path/to/harness/services/api-server
command -v hao
```

The resolved binary should point into the `@harness/hao` install tree.

## Local install from this repository

```bash
npm install -g /path/to/harness/services/api-server
hao --help
hao -v
hao --version
hao version
hao login --api-url http://127.0.0.1:8000 --token <token>
hao status
hao logout
hao doctor
```

## Published package install

After publishing this package to npm:

```bash
npm install -g @harness/hao
hao --help
hao --version
```

Until the package is published, generated local-Agent pairing commands should
use this directory as the npx package spec, for example:

```bash
npx -y /path/to/harness/services/api-server bridge pair --api http://127.0.0.1:8000 --pair-token <token> --pair-code <code> --daemon
```

The generic command discovers installed local Agents first. Discovered
connections stay in `pending_confirmation` until the user selects them in Agent
Studio; unconfirmed bridge daemons heartbeat for discovery but do not pull tasks.

Set `LOCAL_AGENT_NPX_PACKAGE=@harness/hao@latest` only after that package exists
in the configured npm registry.

`hao logout` clears the persisted token in `~/.hao/config.toml` and keeps the
saved API URL. `HAO_API_URL` and `HAO_API_TOKEN` still override the file when
they are set.

## Common usage

```bash
hao auth set --api-url http://127.0.0.1:8000 --token <token>
hao --cwd /path/to/workspace --mode confirm --target host
hao plan --cwd /path/to/workspace "draft a plan"
hao act --cwd /path/to/workspace "make the change and verify it"
```

`hao` still uses the local Python implementation under `app/cli/hao`.
The npm package is only the installable launcher surface.
