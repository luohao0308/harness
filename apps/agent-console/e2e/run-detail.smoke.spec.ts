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

const API_RE = /http:\/\/127\.0\.0\.1:8000\/api\/.*/;

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
      request_json: {},
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
    await expect(page.getByText("ON", { exact: true })).toBeVisible();
  });

  test("Plan DAG shows steps with execution mode, tool hints, sandbox, and subagent evidence", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    // Plan DAG section
    await expect(page.getByText("Plan DAG")).toBeVisible();
    await expect(page.getByText("2 steps")).toBeVisible();

    // Step 1
    await expect(page.getByText("read-readme")).toBeVisible();
    await expect(page.getByText("Read the project README for context")).toBeVisible();
    await expect(page.locator("#plan").getByText("read_file")).toBeVisible();

    // Step 2 with sandbox and subagent badges
    await expect(page.getByText("sandbox-exec")).toBeVisible();
    await expect(page.locator("#plan").getByText("Sandbox", { exact: true })).toBeVisible();
    await expect(page.locator("#plan").getByText("Subagent", { exact: true })).toBeVisible();
    await expect(page.locator("#plan").getByText("async")).toBeVisible();
  });

  test("Tool Calls, Guardrails, Event Stream, and Model Calls are visible", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    // Tool Calls table
    await expect(page.getByText("Tool Calls")).toBeVisible();
    await expect(page.getByText("read_file").first()).toBeVisible();
    await expect(page.getByText("35ms")).toBeVisible();

    // Guardrails (Approvals)
    await expect(page.getByText("Guardrails")).toBeVisible();
    await expect(page.getByText("Low-risk file read")).toBeVisible();

    // Event Stream
    await expect(page.getByText("Event Stream")).toBeVisible();
    await expect(page.getByText("PLAN_CREATED")).toBeVisible();
    await expect(page.getByText("STEP_COMPLETED")).toBeVisible();

    // Model Calls
    await expect(page.getByText("Model Calls")).toBeVisible();
    await expect(page.getByText("300 tokens")).toBeVisible(); // 200 + 100
    await expect(page.getByText("850ms")).toBeVisible();
  });

  test("Replay returns and renders sequence, state summary, and diagnosis", async ({
    page,
  }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}`);

    // Replay panel
    await expect(page.getByText("Replay")).toBeVisible();
    await expect(page.getByText("latest #3")).toBeVisible();

    // Click replay
    await page.getByRole("button", { name: /Replay|重放/ }).click();

    // Replay result
    await expect(page.getByText("replayed")).toBeVisible();
    await expect(
      page.getByText("All steps completed successfully. Harness chain validated."),
    ).toBeVisible();
    await expect(
      page.getByText("No failures detected. Run completed with full evidence."),
    ).toBeVisible();
  });

  test("/runs/:runId/events shows event-focused evidence", async ({ page }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}/events`);

    await expect(page.getByText("Event Stream")).toBeVisible();
    await expect(page.getByText("PLAN_CREATED")).toBeVisible();
    await expect(page.getByText("STEP_COMPLETED")).toBeVisible();
    await expect(page.getByText("TOOL_CALL")).toBeVisible();
  });

  test("/runs/:runId/subagents shows subagent-focused evidence", async ({ page }) => {
    await page.goto(`/runs/${STABLE_RUN_ID}/subagents`);

    await expect(page.getByText("Subagents").last()).toBeVisible();
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
      await fulfillJson(route, { items: [] });
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
