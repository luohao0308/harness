/**
 * L2 Mocked Browser Test: P7 Knowledge Demo Projection
 *
 * Proves the deterministic local seed contract projects through Agent Studio,
 * Workspace, Run Detail, Eval, and Observability without relying on live
 * provider credentials.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/127\.0\.0\.1:8000\/api\/.*/;
const CHAT_STREAM_RE =
  /http:\/\/127\.0\.0\.1:8000\/api\/agents\/default\/runs\/chat\/stream/;

const now = "2026-05-18T00:00:00.000Z";
const runId = "p7-demo-run-00000000-0000-4000-8000-000000000001";
const retrievalSessionId = "p7-demo-retrieval-0000000000001";
const promptManifestId = "p7-demo-prompt-000000000000001";
const retrievalHitId = "p7-demo-hit-00000000000000001";
const citationId = "p7-demo-citation-000000000001";

const agentsFixture = {
  items: [
    {
      id: "default",
      name: "Default Agent",
      description: "P7 release demo agent",
      status: "active",
      role: "executor",
      model_name: "deepseek-v4-flash",
      model_provider: "deepseek-flash",
      max_parallel_assignments: 2,
      tools_json: ["read_file", "web_search"],
      routing_tags: ["p7-demo"],
    },
  ],
  next_cursor: null,
};

const agentFixture = {
  ...agentsFixture.items[0],
  system_prompt: "Use local knowledge evidence for P7 demo answers.",
  created_at: now,
  updated_at: now,
};

const knowledgeFixture = {
  items: [
    {
      id: "p7-demo-agent-source",
      organization_id: "dev-org",
      agent_id: "default",
      name: "P7 Demo Agent Runbook",
      description: "P7 deterministic local demo seed. Fixture evidence only.",
      source_type: "markdown",
      status: "ACTIVE",
      version: 1,
      scope: "agent",
      expires_at: null,
      disabled_at: null,
      archived_at: null,
      last_indexed_at: now,
      last_ingestion_error: null,
      health_status: "HEALTHY",
      settings_json: {},
      metadata_json: {},
      idempotency_key: "p7-seed-fixture:agent:agent-runbook",
      created_by: "dev-admin",
      created_at: now,
      updated_at: now,
      latest_documents: [
        {
          id: "p7-demo-agent-document",
          source_id: "p7-demo-agent-source",
          organization_id: "dev-org",
          agent_id: "default",
          title: "P7 Demo Agent Runbook",
          uri: "seed-fixture://agent-knowledge-harness/p7/agent-runbook",
          content_sha256: "p7-demo-agent-document-sha",
          mime_type: "text/markdown",
          status: "INDEXED",
          version: 1,
          logical_document_id: "p7-demo-agent-document",
          supersedes_document_id: null,
          superseded_at: null,
          ingestion_error: null,
          metadata_json: {},
          idempotency_key: "p7-seed-fixture:agent:agent-runbook",
          created_by: "dev-admin",
          created_at: now,
          updated_at: now,
          indexed_at: now,
          chunk_count: 2,
        },
      ],
    },
    {
      id: "p7-demo-org-source",
      organization_id: "dev-org",
      agent_id: null,
      name: "P7 Demo Org Handoff",
      description: "P7 deterministic local demo seed. Fixture evidence only.",
      source_type: "markdown",
      status: "ACTIVE",
      version: 1,
      scope: "org",
      expires_at: null,
      disabled_at: null,
      archived_at: null,
      last_indexed_at: now,
      last_ingestion_error: null,
      health_status: "HEALTHY",
      settings_json: {},
      metadata_json: {},
      idempotency_key: "p7-seed-fixture:org:org-handoff",
      created_by: "dev-admin",
      created_at: now,
      updated_at: now,
      latest_documents: [
        {
          id: "p7-demo-org-document",
          source_id: "p7-demo-org-source",
          organization_id: "dev-org",
          agent_id: null,
          title: "P7 Demo Org Handoff",
          uri: "seed-fixture://agent-knowledge-harness/p7/org-handoff",
          content_sha256: "p7-demo-org-document-sha",
          mime_type: "text/markdown",
          status: "INDEXED",
          version: 1,
          logical_document_id: "p7-demo-org-document",
          supersedes_document_id: null,
          superseded_at: null,
          ingestion_error: null,
          metadata_json: {},
          idempotency_key: "p7-seed-fixture:org:org-handoff",
          created_by: "dev-admin",
          created_at: now,
          updated_at: now,
          indexed_at: now,
          chunk_count: 1,
        },
      ],
    },
  ],
  next_cursor: null,
};

const workspaceFixture = {
  run: {
    id: runId,
    title: "P7 Knowledge Demo",
    goal: "What evidence proves the Agent Knowledge Harness demo is grounded?",
    status: "COMPLETED",
    model_provider: "deepseek-flash",
    model_name: "deepseek-v4-flash",
    max_runtime_seconds: 300,
    max_subagents: 2,
    enable_sandbox: false,
    enable_network: false,
    created_at: now,
    updated_at: now,
    completed_at: now,
  },
  plan: null,
  events: [],
  knowledge_grounding: {
    retrieval_session: {
      id: retrievalSessionId,
      query:
        "What evidence proves the Agent Knowledge Harness demo is grounded?",
      mode: "local",
      local_status: "sufficient",
      vector_capability: "available",
      strategy: "lexical",
      min_hits: 1,
      min_score: 0.62,
      max_local_chunks: 6,
      max_web_results: 0,
      metadata_json: {
        grounding_provider: "local_knowledge",
        fixture_grounded: true,
        verified_grounded: false,
        grounding_verification_reason: "seed_fixture_local_evidence",
      },
      created_at: now,
    },
    retrieval_hits: [
      {
        id: retrievalHitId,
        chunk_id: "p7-demo-chunk-1",
        web_source_id: null,
        rank: 1,
        score: 0.98,
        source_kind: "knowledge_chunk",
        document_id: "p7-demo-agent-document",
        document_version: 1,
        snippet:
          "P7 deterministic local demo seed projects through Run Detail evidence.",
        metadata_json: {},
        created_at: now,
      },
    ],
    citations: [
      {
        id: citationId,
        retrieval_hit_id: retrievalHitId,
        citation_key: "[1]",
        source_kind: "knowledge_chunk",
        chunk_id: "p7-demo-chunk-1",
        web_source_id: null,
        claim_text: "P7 demo is locally grounded.",
        quoted_text:
          "P7 deterministic local demo seed projects through Run Detail evidence.",
        confidence: 0.98,
        metadata_json: {},
        created_at: now,
      },
    ],
    prompt_manifest: {
      id: promptManifestId,
      retrieval_session_id: retrievalSessionId,
      run_id: runId,
      grounding_correlation_id: retrievalSessionId,
      query:
        "What evidence proves the Agent Knowledge Harness demo is grounded?",
      included_retrieval_hit_ids_json: [retrievalHitId],
      omitted_candidates_json: [],
      source_snapshots_json: [],
      token_budget_json: {},
      prompt_sections_json: [],
      evidence_text_sha256: "p7-demo-evidence-sha",
      metadata_json: {
        grounding_provider: "local_knowledge",
        fixture_grounded: true,
        verified_grounded: false,
        grounding_verification_reason: "seed_fixture_local_evidence",
      },
      created_at: now,
    },
    policy_audits: [
      {
        id: "p7-demo-policy-audit-1",
        retrieval_session_id: retrievalSessionId,
        run_id: runId,
        decision: "allowed",
        reason: "selected_for_prompt",
        source_kind: "knowledge_chunk",
        source_ref_id: "p7-demo-chunk-1",
        safe_metadata_json: {},
        created_at: now,
      },
    ],
    web_sources: [],
    vector_capability: "available",
    local_status: "sufficient",
    grounded: true,
    grounding_provider: "local_knowledge",
    fixture_grounded: true,
    verified_grounded: false,
    grounding_verification_reason: "seed_fixture_local_evidence",
    evidence_summary: "Local fixture knowledge grounded the P7 demo answer.",
    inferred_fallback: false,
    fallback_reason: null,
    selected_retrieval_session_id: retrievalSessionId,
    selected_prompt_manifest_id: promptManifestId,
  },
  subagents: [],
  tool_calls: [],
  model_calls: [],
  approvals: [],
  assignments: [],
  handoffs: [],
};

const datasetsFixture = {
  items: [
    {
      id: "p7-demo-dataset",
      name: "P7 Demo Grounding Dataset",
      description: "Deterministic P7 local fixture eval",
      case_count: 1,
      baseline_run_id: "p7-demo-eval-run",
      created_at: now,
    },
  ],
  next_cursor: null,
};

const casesFixture = {
  items: [
    {
      id: "p7-demo-case",
      dataset_id: "p7-demo-dataset",
      source_task_id: runId,
      input_json: { goal: "What evidence proves the demo is grounded?" },
      expected_json: {
        status: "COMPLETED",
        grounding_contract: {
          retrieval_session_id: retrievalSessionId,
          prompt_manifest_id: promptManifestId,
          citation_keys: ["[1]"],
        },
      },
      tags_json: ["p7-demo", "seed-fixture"],
      created_at: now,
    },
  ],
  next_cursor: null,
};

const evalRunsFixture = {
  items: [
    {
      id: "p7-demo-eval-run",
      dataset_id: "p7-demo-dataset",
      agent_id: "default",
      status: "COMPLETED",
      metrics_json: {
        case_total: 1,
        passed_total: 1,
        task_success_rate: 1,
        grounding_pass_rate: 1,
        citation_coverage_rate: 1,
        unsupported_marker_rate: 0,
        fallback_mismatch_rate: 0,
        forbidden_evidence_leak_rate: 0,
        required_evidence_miss_rate: 0,
        grounding_failure_total: 0,
      },
      results: [
        {
          id: "p7-demo-eval-result",
          status: "PASSED",
          task_id: runId,
          scores_json: { task_success: 1 },
          grader_trace_json: {
            grader: "grounding-trace-v1",
            passed: true,
            grounding_failures: [],
            forbidden_evidence_leaked: false,
            forbidden_leak_sources: [],
            citation_keys: ["[1]"],
            citation_hit_ids: [retrievalHitId],
            retrieval_session_id: retrievalSessionId,
            prompt_manifest_id: promptManifestId,
          },
        },
      ],
      created_at: now,
    },
  ],
  next_cursor: null,
};

const regressionFixture = {
  task_success_rate_delta: 0,
  tool_selection_accuracy_delta: 0,
  avg_latency_ms_delta: 0,
  grounding_pass_rate_delta: 0,
  citation_coverage_rate_delta: 0,
  unsupported_marker_rate_delta: 0,
  fallback_mismatch_rate_delta: 0,
  forbidden_evidence_leak_rate_delta: 0,
  required_evidence_miss_rate_delta: 0,
  is_regression: false,
  newly_failing_case_ids: [],
  newly_passing_case_ids: [],
  newly_grounding_failing_case_ids: [],
  newly_forbidden_leak_case_ids: [],
  low_sample_count: false,
  low_sample_caveat: null,
  grounding_sample_count: 1,
};

const groundingQualityFixture = {
  items: [
    {
      eval_run_id: "p7-demo-eval-run",
      eval_result_id: "p7-demo-eval-result",
      eval_case_id: "p7-demo-case",
      task_id: runId,
      dataset_id: "p7-demo-dataset",
      agent_id: "default",
      status: "PASSED",
      created_at: now,
      grounding_passed: true,
      grounding_failures: [],
      forbidden_evidence_leaked: false,
      forbidden_leak_sources: [],
      fallback_expected: false,
      fallback_observed: false,
      unsupported_marker_present: false,
      citation_keys: ["[1]"],
      citation_hit_ids: [retrievalHitId],
      retrieval_session_id: retrievalSessionId,
      prompt_manifest_id: promptManifestId,
    },
  ],
  metrics: {
    grounding_pass_rate: 1,
    citation_coverage_rate: 1,
    forbidden_evidence_leak_rate: 0,
    fallback_mismatch_rate: 0,
    unsupported_marker_rate: 0,
    grounding_failure_total: 0,
  },
  failure_facets: [],
  total: 1,
};

test.describe("P7 Knowledge demo release smoke", () => {
  test.beforeEach(async ({ page }) => {
    assertFixturesDoNotExposeScrubbedPayloads();
    await routeKnowledgeDemoApis(page);
  });

  test("Agent Studio projects deterministic seed sources and fixture origin", async ({
    page,
  }) => {
    await page.goto("/agents");

    await expect(page.getByText("P7 Demo Agent Runbook").first()).toBeVisible();
    await expect(page.getByText("P7 Demo Org Handoff").first()).toBeVisible();
    await expect(page.getByLabel("编辑知识源说明")).toHaveValue(
      /Fixture evidence only/,
    );
    await expect(
      page.getByRole("button", {
        name: /P7 Demo Agent Runbook.*agent.*HEALTHY/,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /P7 Demo Org Handoff.*org.*HEALTHY/ }),
    ).toBeVisible();
    await expect(page.getByText("2 chunks").first()).toBeVisible();
    await page.getByRole("button", { name: /P7 Demo Org Handoff.*org.*HEALTHY/ }).click();
    await expect(page.getByText("P7 Demo Org Handoff").first()).toBeVisible();
    await expect(page.getByText("1 chunks").first()).toBeVisible();
  });

  test("Workspace projects local fixture grounding indicator", async ({
    page,
  }) => {
    await page.goto("/agents/default/workspace");

    const composer = page.getByPlaceholder("直接与智能体对话");
    await composer.fill(
      "What evidence proves the Agent Knowledge Harness demo is grounded?",
    );
    await page.locator('button[aria-label="发送"]').click();

    await expect(
      page.getByText("Local fixture knowledge grounded the P7 demo answer."),
    ).toBeVisible();
    await expect(page.getByText("The answer is grounded in")).toBeVisible();
    await expect(page.locator('a[aria-label="运行详情"]')).toBeVisible();
  });

  test("Run Detail projects retrieval, citation, and prompt manifest evidence", async ({
    page,
  }) => {
    await page.goto(`/runs/${runId}`);

    await expect(page.getByText("知识依据")).toBeVisible();
    await expect(page.getByText("local_knowledge")).toBeVisible();
    await expect(page.getByText("seed_fixture_local_evidence")).toBeVisible();
    await expect(page.getByText(promptManifestId).first()).toBeVisible();
    await expect(page.getByText(retrievalHitId).first()).toBeVisible();
    await expect(
      page
        .getByText(
          "P7 deterministic local demo seed projects through Run Detail evidence.",
        )
        .first(),
    ).toBeVisible();
  });

  test("Eval and Observability project Eval-owned grounding quality", async ({
    page,
  }) => {
    await page.goto("/evals");

    await expect(page.getByText("P7 Demo Grounding Dataset")).toBeVisible();
    await expect(page.getByText("Grounding 通过率")).toBeVisible();
    await expect(page.getByText("引用覆盖率")).toBeVisible();
    await expect(page.getByText("grounding-trace-v1")).toBeVisible();

    await page.goto("/observability");
    await expect(page.getByText("Grounding Quality")).toBeVisible();
    await expect(page.getByText("100.0%").first()).toBeVisible();
    await expect(page.getByText("clear").first()).toBeVisible();
    await expect(
      page.getByText(`hits ${retrievalHitId}`).first(),
    ).toBeVisible();
  });
});

async function routeKnowledgeDemoApis(page: Page): Promise<void> {
  await page.route(API_RE, async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (CHAT_STREAM_RE.test(route.request().url())) {
      await fulfillSseStream(route);
      return;
    }

    if (path === "/api/agents" && method === "GET") {
      await fulfillJson(route, agentsFixture);
      return;
    }

    if (path === "/api/agents/default" && method === "GET") {
      await fulfillJson(route, agentFixture);
      return;
    }

    if (path === "/api/settings/models" && method === "GET") {
      await fulfillJson(route, {
        default_provider: "deepseek-flash",
        default_model: "deepseek-v4-flash",
        providers: [
          {
            name: "deepseek-flash",
            label: "DeepSeek Flash",
            model: "deepseek-v4-flash",
          },
        ],
        rate_limits: { rpm: 60, tpm: 60_000 },
        health: { status: "healthy" },
        circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
      });
      return;
    }

    if (path === "/api/tools/registry" && method === "GET") {
      await fulfillJson(route, { items: [], categories: [], sources: [] });
      return;
    }

    if (path === "/api/agents/default/knowledge/sources" && method === "GET") {
      await fulfillJson(route, knowledgeFixture);
      return;
    }

    if (
      path ===
        "/api/agents/default/knowledge/sources/p7-demo-agent-source/documents" &&
      method === "GET"
    ) {
      await fulfillJson(route, knowledgeFixture.items[0].latest_documents);
      return;
    }

    if (
      path ===
        "/api/agents/default/knowledge/sources/p7-demo-org-source/documents" &&
      method === "GET"
    ) {
      await fulfillJson(route, knowledgeFixture.items[1].latest_documents);
      return;
    }

    if (path === `/api/agents/runs/${runId}/workspace` && method === "GET") {
      await fulfillJson(route, workspaceFixture);
      return;
    }

    if (path === "/api/evals/datasets" && method === "GET") {
      await fulfillJson(route, datasetsFixture);
      return;
    }

    if (
      path.match(/^\/api\/evals\/datasets\/[^/]+\/cases$/) &&
      method === "GET"
    ) {
      await fulfillJson(route, casesFixture);
      return;
    }

    if (path === "/api/evals/runs" && method === "GET") {
      await fulfillJson(route, evalRunsFixture);
      return;
    }

    if (
      path.match(/^\/api\/evals\/runs\/[^/]+\/regression$/) &&
      method === "GET"
    ) {
      await fulfillJson(route, regressionFixture);
      return;
    }

    if (path === "/api/observability/summary" && method === "GET") {
      await fulfillJson(route, {
        task_total: 1,
        failed_task_total: 0,
        event_total: 12,
        model_call_total: 1,
        tool_call_total: 0,
        sandbox_total: 0,
        active_runs: 0,
        tasks_by_status: [{ label: "COMPLETED", count: 1 }],
        subagents_by_status: [],
        agent_assignments_by_status: [],
        model_calls_by_status: [{ label: "COMPLETED", count: 1 }],
        tool_calls_by_status: [],
        subagent_queue: { pending: 0, running: 0, timeout_count: 0 },
        assignment_queue: { pending: 0, running: 0 },
        warm_pool: {
          enabled: true,
          idle: 0,
          busy: 0,
          failed: 0,
          min_size: 2,
          max_size: 5,
          hit_total: 0,
          miss_total: 0,
        },
        sandboxes_by_status: [],
      });
      return;
    }

    if (path === "/api/observability/grounding-quality" && method === "GET") {
      await fulfillJson(route, groundingQualityFixture);
      return;
    }

    if (
      [
        "/api/observability/services/health",
        "/api/observability/grafana/dashboards",
        "/api/observability/exports",
        "/api/observability/exports/history",
        "/api/observability/logs",
        "/api/subagents/recovery/summary",
      ].includes(path) &&
      method === "GET"
    ) {
      await fulfillJson(route, emptyPageFor(path));
      return;
    }

    if (
      path.startsWith("/api/subagents/recovery/global-summary") &&
      method === "GET"
    ) {
      await fulfillJson(route, {
        organization_count: 0,
        batch_total: 0,
        recovered_total: 0,
        organizations: [],
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: `Unhandled e2e API route: ${path}` }),
    });
  });
}

async function fulfillSseStream(route: Route): Promise<void> {
  const body = [
    sseFrame("run_created", {
      run_id: runId,
      status: "PLANNED",
      step_count: 1,
      message: "Run created",
    }),
    sseFrame("delta", {
      content: "The answer is grounded in local fixture knowledge [1].",
    }),
    sseFrame("done", {
      run_id: runId,
      status: "COMPLETED",
      step_count: 1,
      message: "Stream complete",
      knowledge_grounding:
        "Local fixture knowledge grounded the P7 demo answer.",
    }),
  ].join("");
  await route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    headers: {
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
    body,
  });
}

function sseFrame(eventType: string, data: Record<string, unknown>): string {
  return `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`;
}

async function fulfillJson(route: Route, payload: unknown): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

function emptyPageFor(path: string): unknown {
  if (path === "/api/observability/services/health") {
    return { services: [] };
  }
  if (path === "/api/subagents/recovery/summary") {
    return {
      batch_total: 0,
      task_total: 0,
      scanned_total: 0,
      recovered_total: 0,
      lock_skipped_total: 0,
      action_counts: {},
      tasks: [],
      recent_batches: [],
      latest_completed_at: null,
    };
  }
  return { items: [] };
}

function assertFixturesDoNotExposeScrubbedPayloads(): void {
  const serialized = JSON.stringify([
    knowledgeFixture,
    workspaceFixture,
    evalRunsFixture,
    groundingQualityFixture,
  ]);
  expect(serialized).not.toContain("classified-source-sentence");
  expect(serialized).not.toContain("raw provider response body");
}
