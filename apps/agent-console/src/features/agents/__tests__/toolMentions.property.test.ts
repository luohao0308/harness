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

  it("does not extract embedded email or handle fragments as tools", () => {
    const tools = [tool("bash"), tool("read_file"), tool("example")];

    expect(
      extractToolMentions(
        "Email ops@bash.com or user@example, but do not run anything",
        tools,
      ),
    ).toEqual([]);
  });

  it("extracts mentions delimited by common punctuation", () => {
    const tools = [tool("bash"), tool("read_file"), tool("list-files")];

    expect(extractToolMentions("Use (@bash), then @read_file.", tools)).toEqual([
      { name: "bash", source: "builtin", payload: { mention: "@bash" } },
      { name: "read_file", source: "builtin", payload: { mention: "@read_file" } },
    ]);
  });

  it("infers list_files for natural-language file listing requests", () => {
    const tools = [tool("read_file"), tool("list_files")];

    expect(extractToolMentions("列出项目文件", tools)).toEqual([
      { name: "list_files", source: "builtin", payload: { mention: "@list_files" } },
    ]);
    expect(extractToolMentions("show workspace files", tools)).toEqual([
      { name: "list_files", source: "builtin", payload: { mention: "@list_files" } },
    ]);
  });

  it("does not infer list_files when the tool is not registered", () => {
    expect(extractToolMentions("列出项目文件", [tool("read_file")])).toEqual([]);
  });

  it("keeps explicit builtin mentions when the registry is still loading", () => {
    expect(extractToolMentions("@list_files", [])).toEqual([
      { name: "list_files", source: "builtin", payload: { mention: "@list_files" } },
    ]);
    expect(extractToolMentions("列出项目文件", [])).toEqual([
      { name: "list_files", source: "builtin", payload: { mention: "@list_files" } },
    ]);
  });

  it("never emits a name outside the registry or known builtin fallback", () => {
    const tools = [tool("bash"), tool("read_file"), tool("list-files")];
    const registryNames = new Set(tools.map((item) => item.name));
    const knownFallbackNames = new Set([
      "list_files",
      "write_file",
      "run_shell",
      "run_tests",
      "network_request",
      "git_command",
      "mcp_context_search",
      "mcp_artifact_put",
    ]);

    fc.assert(
      fc.property(fc.string(), (content) => {
        const mentions = extractToolMentions(content, tools);
        for (const mention of mentions) {
          expect(registryNames.has(mention.name) || knownFallbackNames.has(mention.name)).toBe(
            true,
          );
        }
      }),
      { numRuns: 200 },
    );
  });
});
