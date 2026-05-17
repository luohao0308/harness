import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ModelCall } from "../../api";
import { ModelCallPanel } from "../ModelCallPanel";

describe("ModelCallPanel", () => {
  it("renders model token counts with Chinese labels", () => {
    const modelCall: ModelCall = {
      id: "model-call-1",
      task_id: "task-1",
      agent_run_id: "run-1",
      trace_id: null,
      model_provider: "test-provider",
      model_name: "test-model",
      status: "SUCCESS",
      prompt_tokens: 10,
      completion_tokens: 20,
      duration_ms: 42,
      grounding_correlation_id: null,
      prompt_manifest_id: null,
      context_manifest_id: null,
      model_request_sha256: null,
      model_request_hash_schema_version: 1,
      request_message_hashes_json: [],
      request_message_hashes_sha256: null,
      hash_recomputability_status: "legacy_not_recomputable",
      attempt_index: 1,
      terminal_status: "success",
      request_json: {},
      response_json: {},
      error_message: null,
      created_at: "2026-05-15T00:00:00Z",
    };

    const { container } = render(
      <MemoryRouter>
        <ModelCallPanel
          modelCalls={[modelCall]}
          toolCalls={[]}
          toolCallFilters={{ limit: 100 }}
          onToolCallFiltersChange={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("标记 30")).toBeInTheDocument();
    expect(container.textContent ?? "").not.toContain("Tokens 30");
  });
});
