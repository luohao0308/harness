import { describe, expect, it } from "vitest";

import type { AgentRunWorkspace, ToolApproval, ToolCall } from "../../../tasks/api";
import {
  mergeApprovalPage,
  optimisticApprovalDecision,
  projectCitationEvidence,
  runDetailValueLabel,
  shortCapability,
  toolOutputSummary,
} from "../RunDetailPage";

function baseWorkspace(): AgentRunWorkspace {
  const toolCall: ToolCall = {
    id: "tool-1",
    tool_name: "run_shell",
    status: "PENDING_APPROVAL",
    risk_level: "high",
    requires_sandbox: true,
    duration_ms: 0,
    output_kind: "json",
    output_summary: "无输出",
    created_at: "2026-05-17T00:00:00Z",
  } as ToolCall;
  const approval: ToolApproval = {
    id: "approval-1",
    task_id: "run-1",
    tool_call_id: "tool-1",
    organization_id: null,
    requested_by: null,
    decided_by: null,
    status: "PENDING",
    risk_level: "high",
    reason: "needs approval",
    request_json: {},
    decision_json: {},
    created_at: "2026-05-17T00:00:00Z",
    decided_at: null,
  };
  return {
    run: { id: "run-1" } as AgentRunWorkspace["run"],
    plan: null,
    events: [],
    knowledge_grounding: null,
    context_assembly: null,
    token_optimization: {},
    subagents: [],
    tool_calls: [toolCall],
    model_calls: [],
    approvals: [approval],
    assignments: [],
    handoffs: [],
  };
}

describe("RunDetailPage helpers", () => {
  it("formats tool output summaries and hash snippets", () => {
    expect(shortCapability("abcdef1234567890fedcba")).toBe("abcdef1234567890fe");
    expect(toolOutputSummary({ status: "APPROVED" } as ToolCall)).toBe("已批准，等待执行");
    expect(toolOutputSummary({ status: "PENDING_APPROVAL" } as ToolCall)).toBe("等待审批");
    expect(runDetailValueLabel("local_knowledge")).toBe("本地知识库");
    expect(runDetailValueLabel("seed_fixture_local_evidence")).toBe("演示夹具本地证据");
    expect(runDetailValueLabel("recomputable_v2")).toBe("可复算 v2");
  });

  it("accepts only safe project citation evidence", () => {
    expect(projectCitationEvidence({
      source_snapshot: {
        project_uri: "project://docs/guide.md",
        project_file_sha256: "A".repeat(64),
        document_version: 3,
      },
    })).toEqual({
      uri: "project://docs/guide.md",
      sha256: "a".repeat(64),
      documentVersion: 3,
    });
    expect(projectCitationEvidence({
      source_snapshot: { project_uri: "project:///Users/private/guide.md" },
    })).toBeNull();
    expect(projectCitationEvidence({
      source_snapshot: { project_relative_path: "../secret.txt" },
    })).toBeNull();
  });

  it("optimistically updates approval and tool call state", () => {
    const workspace = baseWorkspace();
    const next = optimisticApprovalDecision(workspace, "approval-1", "APPROVED");
    expect(next?.approvals[0].status).toBe("APPROVED");
    expect(next?.tool_calls[0].status).toBe("APPROVED");
  });

  it("merges approval pages back into workspace state", () => {
    const workspace = baseWorkspace();
    const next = mergeApprovalPage(workspace, [
      { ...workspace.approvals[0], status: "APPROVED", decided_at: "2026-05-17T00:01:00Z" },
    ]);
    expect(next?.approvals[0].status).toBe("APPROVED");
    expect(next?.tool_calls[0].status).toBe("APPROVED");
    expect(next?.tool_calls[0].error_message).toBeNull();
  });
});
