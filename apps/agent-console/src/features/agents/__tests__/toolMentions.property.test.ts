// Feature: agent-workspace-chat-v4-refine, Property P24
import { describe, expect, it } from "vitest";
import fc from "fast-check";

import type { ToolMetadata } from "../../tasks/api";
import { extractToolMentions } from "../lib/toolMentions";

function tool(name: string, source = "builtin"): ToolMetadata {
  return {
    name,
    source,
    description: name,
    category: "test",
    risk_level: "low",
    requires_sandbox: false,
    network_policy: "none",
    timeout_seconds: 1,
    allowed_roles: [],
    audit_level: "summary",
    idempotent: true,
    input_schema: {},
    mcp_server: null,
    mcp_method: null,
  };
}

describe("Property P24: tool mentions serialize structured payloads", () => {
  it("extracts only registered @tool names and preserves registry order", () => {
    const tools = [tool("bash"), tool("read_file"), tool("list-files")];

    expect(extractToolMentions("Use @bash then @missing and @read_file", tools)).toEqual([
      { name: "bash", source: "builtin", payload: { mention: "@bash" } },
      { name: "read_file", source: "builtin", payload: { mention: "@read_file" } },
    ]);
  });

  it("deduplicates repeated mentions", () => {
    expect(extractToolMentions("@bash @bash @bash", [tool("bash")])).toEqual([
      { name: "bash", source: "builtin", payload: { mention: "@bash" } },
    ]);
  });

  it("never emits a name outside the registry", () => {
    const tools = [tool("bash"), tool("read_file"), tool("list-files")];
    const registryNames = new Set(tools.map((item) => item.name));

    fc.assert(
      fc.property(fc.string(), (content) => {
        const mentions = extractToolMentions(content, tools);
        for (const mention of mentions) {
          expect(registryNames.has(mention.name)).toBe(true);
        }
      }),
      { numRuns: 200 },
    );
  });
});
