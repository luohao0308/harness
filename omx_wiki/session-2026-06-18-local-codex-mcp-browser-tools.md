# Local Codex MCP Browser Tools

Category: `session-log`

Tags: `local-dev`, `codex`, `mcp`, `playwright`, `chrome-devtools`

## Summary

User-level Codex MCP configuration now includes two browser automation/debugging servers:

- `playwright` backed by `@playwright/mcp@0.0.76`
- `chrome_devtools` backed by `chrome-devtools-mcp@1.3.0`

Both packages were installed globally under Node v24.15.0 because `chrome-devtools-mcp` requires a newer Node runtime than the existing OMX Node v20.9.0 install.

2026-06-19 refresh: `chrome-devtools-mcp` was updated from `1.2.0` to `1.3.0`, and the user-level Codex MCP tables were restored directly in `~/.codex/config.toml` after `codex mcp add` reported success without leaving entries visible to `codex mcp list`.

## Configuration

`~/.codex/config.toml` now contains enabled stdio MCP servers:

```text
[mcp_servers.playwright]
command = "/Users/luohao/.nvm/versions/node/v24.15.0/bin/playwright-mcp"
args = ["--browser", "chrome", "--headless", "--isolated", "--output-dir", "/Users/luohao/.codex/mcp-output/playwright"]

[mcp_servers.chrome_devtools]
command = "/Users/luohao/.nvm/versions/node/v24.15.0/bin/chrome-devtools-mcp"
args = ["--headless", "--isolated", "--viewport", "1280x720", "--no-usage-statistics"]

env = { CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS = "1" }
```

## Validation

```text
/Users/luohao/.nvm/versions/node/v24.15.0/bin/npm list -g --depth=0 @playwright/mcp chrome-devtools-mcp
@playwright/mcp@0.0.76
chrome-devtools-mcp@1.3.0

/Users/luohao/.nvm/versions/node/v24.15.0/bin/playwright-mcp --version
Version 0.0.76

/Users/luohao/.nvm/versions/node/v24.15.0/bin/chrome-devtools-mcp --version
1.3.0

codex mcp list
playwright enabled
chrome_devtools enabled

MCP initialize plus tools/list smoke
playwright: 23 tools
chrome_devtools: 29 tools
```

## Notes

This was an environment/configuration change only. No product runtime code was modified.
