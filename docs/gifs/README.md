# GIF Capture List

Store short product walkthrough GIFs here when the release operator captures
them from the private deployment:

- docker-compose-up.gif
- first-agent-run.gif
- cost-dashboard.gif

Keep each GIF under 5 MB. Use WebM links in README when a recording exceeds
that limit.

## Current Capture Status

```yaml
updated_at: "2026-06-21T04:26:00+08:00"
first_agent_run:
  status: captured
  gif: docs/gifs/first-agent-run.gif
  screenshot: docs/gifs/first-agent-run-screenshot.png
  size: "2.1 MB"
  recording_source: "Playwright Chromium browser video converted with ffmpeg"
  flow:
    - open Agent Console
    - enter /agents
    - open default Agent Workspace
    - send one Agent Run request
    - view tool/artifact stream evidence
    - open Run Detail
    - view Plan dependency graph and event/tool evidence
  boundary: "Local mocked SSE/API demo capture; no external model provider or Docker worker was used."
desktop_capture:
  ffmpeg: available
  screencapture: "available but returned capture error during this session"
  docker_compose: "available (Docker Compose v2.23.0-desktop.1)"
```
