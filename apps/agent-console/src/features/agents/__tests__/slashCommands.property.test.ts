// Feature: agent-workspace-chat-v3-slash-history, Properties P12/P13/P14
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import {
  SLASH_COMMANDS,
  filterCommandsByPrefix,
  parseSlashCommand,
  replaceSlashPrefix,
} from "../lib/slashCommands";

/**
 * P12 — parseSlashCommand is TOTAL for any string input.
 * P13 — parseSlashCommand is a pure function (idempotent result).
 * P14 — confirmed results strip the /command prefix and normalise args.
 */
describe("Property P12: parseSlashCommand is TOTAL", () => {
  it("never throws for arbitrary strings", () => {
    fc.assert(
      fc.property(fc.string(), (draft) => {
        expect(() => parseSlashCommand(draft)).not.toThrow();
      }),
      { numRuns: 200 },
    );
  });

  it("returns { kind: 'none' } whenever draft does not start with /", () => {
    fc.assert(
      fc.property(fc.string(), (draft) => {
        if (draft.length === 0 || draft.charAt(0) !== "/") {
          expect(parseSlashCommand(draft).kind).toBe("none");
        }
      }),
      { numRuns: 200 },
    );
  });

  it("returns { kind: 'none' } whenever draft contains a newline", () => {
    fc.assert(
      fc.property(fc.string(), fc.string(), (prefix, suffix) => {
        const draft = `/${prefix}\n${suffix}`;
        expect(parseSlashCommand(draft).kind).toBe("none");
      }),
      { numRuns: 200 },
    );
  });
});

describe("Property P13: parseSlashCommand is idempotent", () => {
  it("returns deep-equal results on back-to-back calls", () => {
    fc.assert(
      fc.property(fc.string(), (draft) => {
        const a = parseSlashCommand(draft);
        const b = parseSlashCommand(draft);
        expect(a).toEqual(b);
      }),
      { numRuns: 200 },
    );
  });
});

describe("Property P14: confirmed results strip the /command prefix", () => {
  it("restDraft is always empty and args has no leading /", () => {
    // Pick a no-args command name from the registry.
    const noArgCmds = SLASH_COMMANDS.filter((c) => !c.needsArgs);
    const names = noArgCmds.map((c) => c.name);
    fc.assert(
      fc.property(
        fc.constantFrom(...names),
        fc.string({ maxLength: 50 }).filter((s) => !s.includes("\n")),
        (name, extra) => {
          // Trailing space turns this into a confirmed dispatch even with
          // no-args commands.
          const draft = extra.length === 0 ? `/${name} ` : `/${name} ${extra}`;
          const result = parseSlashCommand(draft);
          expect(result.kind).toBe("confirmed");
          if (result.kind === "confirmed") {
            expect(result.restDraft).toBe("");
            expect(result.command.name).toBe(name);
            expect(result.args.startsWith("/")).toBe(false);
          }
        },
      ),
      { numRuns: 200 },
    );
  });

  it("needsArgs commands require a non-empty arg to be confirmed", () => {
    const toolCmd = SLASH_COMMANDS.find((c) => c.name === "tool");
    expect(toolCmd).toBeDefined();
    expect(parseSlashCommand("/tool").kind).toBe("matching");
    expect(parseSlashCommand("/tool ").kind).toBe("matching");
    const confirmed = parseSlashCommand("/tool curl");
    expect(confirmed.kind).toBe("confirmed");
    if (confirmed.kind === "confirmed") {
      expect(confirmed.command.name).toBe("tool");
      expect(confirmed.args).toBe("curl");
    }
  });

  it("aliases resolve to the canonical command", () => {
    const result = parseSlashCommand("/plan-md ");
    expect(result.kind).toBe("confirmed");
    if (result.kind === "confirmed") {
      expect(result.command.name).toBe("codex");
    }
  });
});

describe("filterCommandsByPrefix: case-insensitive + alias aware", () => {
  it("empty prefix returns the whole registry preserving order", () => {
    const out = filterCommandsByPrefix("");
    expect(out).toEqual(SLASH_COMMANDS);
  });

  it("prefix matches canonical name case-insensitively", () => {
    const out = filterCommandsByPrefix("PL");
    expect(out.map((c) => c.name)).toContain("plan");
  });

  it("prefix matches alias", () => {
    const out = filterCommandsByPrefix("plan-");
    expect(out.map((c) => c.name)).toContain("codex");
  });
});

describe("replaceSlashPrefix: retains trailing arguments", () => {
  it("replaces the first /xxx segment keeping any trailing text", () => {
    expect(replaceSlashPrefix("/pl", "plan")).toBe("/plan ");
    expect(replaceSlashPrefix("/pl curl", "tool")).toBe("/tool curl");
    expect(replaceSlashPrefix("", "plan")).toBe("/plan ");
    expect(replaceSlashPrefix("no-slash", "plan")).toBe("/plan ");
  });
});
