# 6. AI-Native, Self-Maintaining Documentation Architecture

Date: 2026-06-20

## Status

Accepted

## Context

The harness documentation is a brownfield system: `docs/ai/` already holds a
startup-context loop (`agent-startup-context.md`), a machine-readable
`context-index.json` consumed by `scripts/agent-context-brief.py` and
`scripts/validate-docs.py`, an `omx_wiki/` knowledge base (~70 session and
handoff pages), and an existing Architecture Decision Record series under
`docs/adr/` (records 0001-0005). CI already enforces documentation invariants
via `scripts/validate-docs.py`.

We need new agents to (a) start from a slim, fast-to-load context, (b) navigate
to the right module and spec quickly, (c) reuse hard-won error/anti-pattern
knowledge, and (d) leave a durable pointer to each session's notes — all
without forking a parallel documentation system, adding runtime dependencies,
or invoking a model at session end.

Two questions drove the design: what machine-readable format backs the module
map, and where do decisions live.

## Decision

1. **Reuse `docs/adr/`, do not create `docs/decisions/`.** The repo already has
   an ADR series (0001-0005). New decisions are appended here as the next
   sequential record (this is 0006). Creating a second decision log would orphan
   the existing five ADRs.

2. **Use JSON for the module map (`docs/module-map.json`), not YAML or TOML.**
   The repo already parses `docs/ai/context-index.json` with the stdlib `json`
   module in two scripts. JSON adds no runtime dependency and no net-new parser.
   YAML would require `PyYAML` (a new dependency) or a hand-rolled parser
   (net-new risk); TOML's `tomllib` is stdlib only on Python 3.11+ and is not
   currently exercised by any project script.

3. **Generate `docs/MODULE-INDEX.md` from `docs/module-map.json`; do not
   hand-author it.** A new `--gen-module-index` flag on
   `scripts/agent-context-brief.py` renders the index deterministically from
   the map. CI guards sync with `git diff --quiet docs/MODULE-INDEX.md`.
   `docs/SPEC-INDEX.md` remains human-authored (curated, feature-keyed) because
   it is editorial, not derivable.

4. **The session-end (Stop) hook is append-only and never calls an LLM.** Each
   session writes its notes to `.omc/state/sessions/{sessionId}/notes.md`
   (per-session, durable, not overwritten); a pure-shell Stop hook appends one
   `- <ISO8601Z> → .omc/state/sessions/{sessionId}/notes.md` line to
   `docs/ai/session-log-pointers.md`. No model call, no network. The brief
   surfaces the last five pointers under a "Recent Sessions" section (behind
   `--show-sessions` flag).

5. **New validator checks parse-and-assert on structure; drift fails the build
   loudly.** `check_frontmatter` parses `---`-delimited blocks into dicts and
   asserts required keys; `check_module_map` parses the JSON and asserts every
   `path`/`docs` entry exists on disk, exiting non-zero on the first miss;
   `check_memory_files` parses markdown headings. None use substring matching.

## Consequences

**Positive**
- No new runtime dependencies; everything runs on the Python 3 stdlib already
  used by project scripts.
- The five existing ADRs and the existing `validate-docs.py` / context-index
  machinery are preserved and extended, not replaced.
- `MODULE-INDEX.md` cannot silently drift from the source map (CI-guarded), and
  a stale module path fails CI with a clear non-zero exit instead of rotting.
- Session close is deterministic and instant (no LLM at teardown).
- The new validator checks set a parse-and-assert precedent for future checks.

**Negative / trade-offs**
- `scripts/agent-context-brief.py` gains a non-default code path
  (`--gen-module-index`, `--show-sessions`); a golden-output test guards the
  default rendering against regressions.
- `docs/module-map.json` must be kept truthful: any real refactor that moves a
  module path requires updating the map (enforced loudly by CI).
- `docs/MODULE-INDEX.md` must only ever be regenerated, never hand-edited.

## Alternatives Considered

- **New `docs/decisions/` + PyYAML for `module-map.yaml`** — rejected: orphans
  the 5 existing ADRs, adds a runtime dependency, and enlarges the
  restructuring surface.
- **Single mega-index + LLM-summarizing Stop hook** — rejected: violates the
  non-negotiable "no LLM at session end" constraint and defeats the slim
  startup-context goal.
- **TOML (`module-map.toml`)** — rejected: `tomllib` is 3.11+ and unexercised
  in project scripts; JSON is already the proven substrate (`context-index.json`).
