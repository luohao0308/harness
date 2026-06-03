/**
 * L2 Mocked Browser Test: Run Detail Product Proof
 *
 * Proves the Run Detail page renders all Harness evidence sections:
 * summary, Plan DAG, Tool Calls, Replay, Guardrails, Event Stream,
 * Subagents, and Model Calls — using typed deterministic fixtures.
 *
 * Also verifies deep-link anchors (#plan, #model-calls, #tool-runtime,
 * #approvals) are present and navigable.
 *
 * Part of the Complete Harness Validation Flow (L2 + L4 layers).
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

const STABLE_RUN_ID = "e2e-run-detail-00000000-0000-0000-0000-000000000002";
const STABLE_TASK_ID = STABLE_RUN_ID; // Run and task share the same id in this system
const now = "2026-05-13T12:00:00.000Z";

// ---------------------------------------------------------------------------
// Typed fixtures matching AgentRunWorkspace shape
// ---------------------------------------------------------------------------

const workspaceFixture = {
  run: {
    id: STABLE_RUN_ID,
    title: "Validate Harness Chain",
    goal: "Prove Model + Harness = Agent end-to-end",
    status: "COMPLETED",
    model_provider: "deepseek-flash",
    model_name: "deepseek-v4-flash",
    max_runtime_seconds: 300,
    max_subagents: 3,
    enable_sandbox: true,
    enable_network: true,
    created_at: now,
    updated_at: now,
    completed_at: now,
  },
  plan: {
    id: "plan-001",
    task_id: STABLE_TASK_ID,
    version: 1,
    status: "COMPLETED",
    summary: "Read file, execute tool, spawn subagent",
    planner_source: "deepseek-v4-flash",
    planner_attempts: 1,
    planner_prompt_version: "v2",
    quality_score: 0.95,
    validation_warnings: [],
    quality_gates: { coverage: true, risk: true },
    plan_json: {},
    steps: [
      {
        step_key: "read-readme",
        description: "Read the project README for context",
        depends_on: [],
        execution_mode: "sync",
        requires_sandbox: false,
        can_spawn_subagent: false,
        tool_hints: ["read_file"],
        acceptance_criteria: ["File content returned"],
        risk_level: "low",
        artifact_expectations: [],
        quality_notes: [],
        status: "COMPLETED",
        assigned_agent_id: null,
        error_message: null,
        trace_summary: null,
        last_event_sequence: 2,
        execution_trace: [],
      },
      {
        step_key: "sandbox-exec",
        description: "Execute validation in sandbox",
        depends_on: ["read-readme"],
        execution_mode: "async",
        requires_sandbox: true,
        can_spawn_subagent: true,
        tool_hints: ["shell_exec"],
        acceptance_criteria: ["Exit code 0"],
        risk_level: "high",
        artifact_expectations: ["validation-report.json"],
        quality_notes: [],
        status: "COMPLETED",
        assigned_agent_id: null,
        error_message: null,
        trace_summary: null,
        last_event_sequence: 5,
        execution_trace: [],
      },
    ],
    created_at: now,
  },
  events: [
    {
      id: "evt-001",
      task_id: STABLE_TASK_ID,
      agent_run_id: STABLE_RUN_ID,
      sequence: 1,
      event_type: "PLAN_CREATED",
      payload_json: {},
      actor_type: "system",
      actor_id: null,
      trace_id: "trace-e2e-detail-001",
      created_at: now,
    },
    {
      id: "evt-002",
      task_id: STABLE_TASK_ID,
      agent_run_id: STABLE_RUN_ID,
      sequence: 2,
      event_type: "STEP_COMPLETED",
      payload_json: { step_key: "read-readme" },
      actor_type: "executor",
      actor_id: null,
      trace_id: "trace-e2e-detail-001",
      created_at: now,
    },
    {
      id: "evt-003",
      task_id: STABLE_TASK_ID,
      agent_run_id: STABLE_RUN_ID,
      sequence: 3,
      event_type: "TOOL_CALL",
      payload_json: { tool_name: "read_file" },
      actor_type: "executor",
      actor_id: null,
      trace_id: "trace-e2e-detail-001",
      created_at: now,
    },
  ],
  knowledge_grounding: {
    retrieval_session: {
      id: "rs-detail-001",
      query: "Validate Harness Chain",
      mode: "local",
      local_status: "sufficient",
      vector_capability: "available",
      strategy: "vector",
      min_hits: 2,
      min_score: 0.62,
      max_local_chunks: 6,
      max_web_results: 0,
      metadata_json: {
        grounding_provider: "local_knowledge",
        fixture_grounded: false,
        verified_grounded: true,
        grounding_verification_reason: "local_evidence_sufficient",
      },
      created_at: now,
    },
    retrieval_hits: [
      {
        id: "rh-detail-001",
        chunk_id: "chunk-detail-001",
        web_source_id: null,
        rank: 1,
        score: 0.97,
        source_kind: "knowledge_chunk",
        document_id: "doc-detail-001",
        document_version: 1,
        snippet: "Harness chain evidence with persisted citations.",
        metadata_json: {},
        created_at: now,
      },
    ],
    citations: [
      {
        id: "cit-detail-001",
        retrieval_hit_id: "rh-detail-001",
        citation_key: "[1]",
        source_kind: "knowledge_chunk",
        chunk_id: "chunk-detail-001",
        web_source_id: null,
        claim_text: "Validate Harness Chain",
        quoted_text: "Harness chain evidence with persisted citations.",
        confidence: 0.97,
        metadata_json: {},
        created_at: now,
      },
    ],
    prompt_manifest: {
      id: "pm-detail-001",
      retrieval_session_id: "rs-detail-001",
      run_id: STABLE_TASK_ID,
      grounding_correlation_id: "rs-detail-001",
      query: "Validate Harness Chain",
      included_retrieval_hit_ids_json: ["rh-detail-001"],
      omitted_candidates_json: [],
      source_snapshots_json: [],
      token_budget_json: {},
      prompt_sections_json: [],
      evidence_text_sha256: "evidence-hash-detail-001",
      metadata_json: {
        grounding_provider: "local_knowledge",
        fixture_grounded: false,
        verified_grounded: true,
        grounding_verification_reason: "local_evidence_sufficient",
      },
      created_at: now,
    },
    policy_audits: [
      {
        id: "audit-detail-001",
        retrieval_session_id: "rs-detail-001",
        run_id: STABLE_TASK_ID,
        decision: "allowed",
        reason: "selected_for_prompt",
        source_kind: "knowledge_chunk",
        source_ref_id: "chunk-detail-001",
        safe_metadata_json: {},
        created_at: now,
      },
    ],
    web_sources: [],
    vector_capability: "available",
    local_status: "sufficient",
    grounded: true,
    grounding_provider: "local_knowledge",
    fixture_grounded: false,
    verified_grounded: true,
    grounding_verification_reason: "local_evidence_sufficient",
    evidence_summary: "Local knowledge grounded the answer.",
    inferred_fallback: false,
    fallback_reason: null,
    selected_retrieval_session_id: "rs-detail-001",
    selected_prompt_manifest_id: "pm-detail-001",
  },
  subagents: [
    {
      id: "sub-001",
      task_id: STABLE_TASK_ID,
      parent_agent_id: "default",
      agent_type: "validator",
      status: "COMPLETED",
      context_json: {},
      started_at: now,
      completed_at: now,
      timeout_at: null,
    },
  ],
  tool_calls: [
    {
      id: "tc-detail-001",
      task_id: STABLE_TASK_ID,
      agent_run_id: STABLE_RUN_ID,
      trace_id: "trace-e2e-detail-001",
      tool_name: "read_file",
      status: "COMPLETED",
      risk_level: "low",
      requires_sandbox: false,
      sandbox_id: null,
      duration_ms: 35,
      input_json: { path: "README.md" },
      output_json: { content: "# Harness" },
      output_kind: "text",
      output_summary: "File content returned",
      timeout_category: null,
      error_message: null,
      created_at: now,
    },
  ],
  model_calls: [
    {
      id: "mc-detail-001",
      task_id: STABLE_TASK_ID,
      agent_run_id: STABLE_RUN_ID,
      trace_id: "trace-e2e-detail-001",
      model_provider: "deepseek-flash",
      model_name: "deepseek-v4-flash",
      status: "COMPLETED",
      prompt_tokens: 200,
      completion_tokens: 100,
      duration_ms: 850,
      grounding_correlation_id: "rs-detail-001",
      prompt_manifest_id: "pm-detail-001",
      model_request_sha256: "request-hash-detail-001",
      model_request_hash_schema_version: 2,
      request_message_hashes_json: [
        {
          index: 0,
          role: "system",
          content_sha256: "message-hash-detail-001",
        },
      ],
      request_message_hashes_sha256: "message-hashes-hash-detail-001",
      hash_recomputability_status: "recomputable_v2",
      attempt_index: 1,
      terminal_status: "success",
      request_json: {
        model_request_sha256: "request-hash-detail-001",
      },
      response_json: {},
      error_message: null,
      created_at: now,
    },
  ],
  approvals: [
    {
      id: "appr-001",
      task_id: STABLE_TASK_ID,
      tool_call_id: "tc-detail-001",
      organization_id: null,
      requested_by: "executor",
      decided_by: "operator",
      status: "APPROVED",
      risk_level: "low",
      reason: "Low-risk file read",
      request_json: {},
      decision_json: {},
      created_at: now,
      decided_at: now,
    },
  ],
  assignments: [],
  handoffs: [],
};

const replayFixture = {
  task_id: STABLE_TASK_ID,
  sequence: 3,
  state_summary: "All steps completed successfully. Harness chain validated.",
  failure_point: null,
  diagnosis: "No failures detected. Run completed with full evidence.",
  requires_manual_review: false,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Run Detail mocked product proof", () => {
  test.beforeEach(async ({ page }) => {
    await routeRunDetailApis(page);
  });

  test("Run Detail shows summary, status, model, sandbox, and subagent capacity", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    // Run summary
    await expect(page.getByText("Validate Harness Chain")).toBeVisible();
    await expect(page.getByText("Prove Model + Harness = Agent end-to-end")).toBeVisible();
    await expect(page.getByText("COMPLETED").first()).toBeVisible();

    // Model info
    await expect(page.getByText("deepseek-flash/deepseek-v4-flash").first()).toBeVisible();

    // Subagent capacity — the Metric component shows "3" for max_subagents
    await expect(page.locator("section").first().getByText("3", { exact: true })).toBeVisible();

    // Sandbox
    await expect(page.getByText("开启", { exact: true })).toBeVisible();
  });

  test("Plan DAG shows steps with execution mode, tool hints, sandbox, and subagent evidence", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    // Plan DAG section
    await expect(page.getByText("计划 DAG")).toBeVisible();
    await expect(page.getByText("2 个步骤")).toBeVisible();

    // Step 1
    await expect(page.getByText("1. read-readme")).toBeVisible();
    await expect(page.getByText("Read the project README for context")).toBeVisible();
    await expect(page.locator("#plan").getByText("read_file")).toBeVisible();
    await expect(page.locator("#plan").getByText("依赖: 无")).toBeVisible();

    // Step 2 with sandbox and subagent badges
    await expect(page.getByText("sandbox-exec")).toBeVisible();
    await expect(page.locator("#plan").getByText("沙箱", { exact: true })).toBeVisible();
    await expect(page.locator("#plan").getByText("子代理", { exact: true })).toBeVisible();
    await expect(page.locator("#plan").getByText("async")).toBeVisible();
    await expect(page.locator("#plan").getByText("依赖: read-readme")).toBeVisible();
  });

  test("Tool Calls, Guardrails, Event Stream, and Model Calls are visible", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    // Tool Calls table
    await expect(page.getByText("工具调用")).toBeVisible();
    await expect(page.getByText("read_file").first()).toBeVisible();
    await expect(page.getByText("35ms")).toBeVisible();

    // Guardrails (Approvals)
    await expect(page.getByText("护栏")).toBeVisible();
    await expect(page.getByText("Low-risk file read")).toBeVisible();

    // Event Stream
    await expect(page.getByText("事件流")).toBeVisible();
    await expect(page.getByText("PLAN_CREATED")).toBeVisible();
    await expect(page.getByText("STEP_COMPLETED")).toBeVisible();

    // Model Calls
    await expect(page.getByText("模型调用")).toBeVisible();
    await expect(page.getByText("300 标记")).toBeVisible(); // 200 + 100
    await expect(page.getByText("850ms")).toBeVisible();
    await expect(page.getByText("pm-detail-001").last()).toBeVisible();
    await expect(page.getByText("request-hash-detail-001")).toBeVisible();
    await expect(page.getByText("recomputable_v2")).toBeVisible();
  });

  test("Knowledge grounding shows provider and verification evidence", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    await expect(page.getByText("知识依据")).toBeVisible();
    await expect(page.getByText("local_knowledge")).toBeVisible();
    await expect(page.getByText("local_evidence_sufficient")).toBeVisible();
    await expect(page.getByText("提示词组装审计")).toBeVisible();
    await expect(page.getByText("pm-detail-001").first()).toBeVisible();
    await expect(
      page.getByText("Harness chain evidence with persisted citations.").first(),
    ).toBeVisible();
  });

  test("Replay returns and renders sequence, state summary, and diagnosis", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    // Replay panel
    await expect(page.getByText("重放").first()).toBeVisible();
    await expect(page.getByText("最新 #3")).toBeVisible();

    // Click replay
    await page.getByRole("button", { name: "重放" }).click();

    // Replay result
    await expect(page.getByText("已重放")).toBeVisible();
    await expect(
      page.getByText("All steps completed successfully. Harness chain validated."),
    ).toBeVisible();
    await expect(
      page.getByText("No failures detected. Run completed with full evidence."),
    ).toBeVisible();
  });

  test("completed runs can be saved as Eval Case after choosing a dataset", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    await page.getByLabel("选择数据集").click();
    await page.getByRole("option", { name: "Smoke Dataset" }).click();
    await page.getByRole("button", { name: "保存为评测用例" }).click();

    await expect(page.getByRole("button", { name: /Saved|已保存/ })).toBeVisible();
  });

  test("/runs/:runId/events shows event-focused evidence", async ({ page }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}/events`);

    await expect(page.getByText("事件流")).toBeVisible();
    await expect(page.getByText("PLAN_CREATED")).toBeVisible();
    await expect(page.getByText("STEP_COMPLETED")).toBeVisible();
    await expect(page.getByText("TOOL_CALL")).toBeVisible();
  });

  test("/runs/:runId/subagents shows subagent-focused evidence", async ({ page }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}/subagents`);

    await expect(page.getByText("子代理").last()).toBeVisible();
    await expect(page.getByText("sub-001".slice(0, 8))).toBeVisible();
    await expect(page.getByText("validator")).toBeVisible();
    await expect(page.getByText("COMPLETED").first()).toBeVisible();
  });

  test("deep-link anchors #plan, #model-calls, #tool-runtime, #approvals exist", async ({
    page,
  }) => {
    // Navigate to each anchor and verify the target element exists
    await page.goto(`/runs/${STABLE_RUN_ID}#plan`);
    await expect(page.locator("#plan")).toBeVisible();

    await page.goto(`/runs/${STABLE_RUN_ID}#model-calls`);
    await expect(page.locator("#model-calls")).toBeVisible();

    await page.goto(`/runs/${STABLE_RUN_ID}#tool-runtime`);
    await expect(page.locator("#tool-runtime")).toBeVisible();

    await page.goto(`/runs/${STABLE_RUN_ID}#approvals`);
    await expect(page.locator("#approvals")).toBeVisible();
  });

  test("fail-closed: unknown API routes return 404", async ({ page }) => {
    const unhandledRoutes: string[] = [];
    page.on("response", (response) => {
      if (
        response.status() === 404 &&
        response.url().includes("/api/") &&
        !response.url().includes("Unhandled")
      ) {
        unhandledRoutes.push(response.url());
      }
    });

    await page.goto(`/runs/${STABLE_RUN_ID}`);
    await expect(page.getByText("Validate Harness Chain")).toBeVisible();
    await page.waitForTimeout(1000);

    // All API routes should be handled by our mocks
    expect(unhandledRoutes).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function routeRunDetailApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    // Workspace projection for Run Detail
    if (path === `/api/agents/runs/${STABLE_RUN_ID}/workspace`) {
      await fulfillJson(route, workspaceFixture);
      return;
    }

    // Replay endpoint
    if (path === `/api/tasks/${STABLE_TASK_ID}/replay` && method === "POST") {
      await fulfillJson(route, replayFixture);
      return;
    }

    // Eval datasets (fetched by "Save as Eval Case" button)
    if (path === "/api/evals/datasets" && method === "GET") {
      await fulfillJson(route, {
        items: [
          {
            id: "dataset-smoke",
            organization_id: null,
            name: "Smoke Dataset",
            description: "Run Detail smoke dataset",
            status: "active",
            baseline_run_id: null,
            created_by: "e2e",
            created_at: now,
            updated_at: now,
            case_count: 0,
          },
        ],
        next_cursor: null,
      });
      return;
    }

    if (
      path === `/api/evals/datasets/dataset-smoke/cases/from-run/${STABLE_TASK_ID}` &&
      method === "POST"
    ) {
      const requestPayload = route.request().postDataJSON() as {
        expected_json: {
          status: string;
          grounding_contract?: Record<string, unknown>;
        };
        tags_json: string[];
      };
      expect(requestPayload.expected_json.grounding_contract).toMatchObject({
        retrieval_session_id: "rs-detail-001",
        prompt_manifest_id: "pm-detail-001",
        require_grounded: true,
        require_prompt_manifest: true,
        require_insufficient: false,
        allow_fixture_grounding: false,
        require_policy_decisions: ["allowed"],
      });
      await fulfillJson(route, {
        id: "case-smoke",
        dataset_id: "dataset-smoke",
        source_task_id: STABLE_TASK_ID,
        input_json: {},
        expected_json: requestPayload.expected_json,
        tags_json: ["saved-from-run"],
        created_at: now,
      });
      return;
    }

    // Fail-closed: return 404 for any unhandled API route
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled e2e API route: ${path}` }),
    });
  });
}

async function fulfillJson(route: Route, payload: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}
