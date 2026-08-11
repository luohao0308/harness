import { expect, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15173|15174)\/api\/.*/;

export const enterpriseIds = {
  agentId: "default",
  teamId: "team-enterprise",
  runId: "run-enterprise",
  subagentId: "subagent-enterprise",
  specialistId: "specialist-enterprise",
  listingId: "listing-enterprise",
  sandboxId: "sandbox-enterprise",
  evalRunId: "eval-enterprise",
  alertRuleId: "alert-enterprise",
  traceId: "trace-enterprise",
  orgId: "dev-org",
};

const now = "2026-05-30T06:33:42.000Z";

export type UnhandledApiRequest = {
  method: string;
  path: string;
  query: string;
  pageUrl: string;
};

export type EnterpriseHarness = {
  unhandledApiRequests: UnhandledApiRequest[];
  assertNoUnhandledApiRequests: () => Promise<void>;
};

export type EnterpriseHarnessOptions = {
  missingModelPricingSources?: boolean;
  expectedApi404Paths?: string[];
};

export async function registerEnterpriseApiRoutes(
  page: Page,
  options: EnterpriseHarnessOptions = {},
): Promise<EnterpriseHarness> {
  const unhandledApiRequests: UnhandledApiRequest[] = [];
  const expectedApi404Paths = new Set(options.expectedApi404Paths ?? []);
  page.on("response", (response) => {
    if (response.status() === 404 && response.url().includes("/api/")) {
      const url = new URL(response.url());
      if (expectedApi404Paths.has(url.pathname)) {
        return;
      }
      const request = response.request();
      unhandledApiRequests.push({
        method: request.method(),
        path: url.pathname,
        query: url.search,
        pageUrl: page.url(),
      });
    }
  });
  await page.routeWebSocket(/ws:\/\/(?:127\.0\.0\.1|localhost):8000\/ws\/terminal(?:\?.*)?$/, (socket) => {
    socket.onMessage(() => undefined);
  });
  await page.route(API_RE, (route) => routeEnterpriseApi(route, options));
  return {
    unhandledApiRequests,
    assertNoUnhandledApiRequests: async () => {
      await page.waitForTimeout(200);
      expect(unhandledApiRequests).toEqual([]);
    },
  };
}

export async function expectNoRouteError(page: Page): Promise<void> {
  await expect(page.locator("body")).not.toContainText("Unhandled e2e API route");
  await expect(page.locator("body")).not.toContainText("Application error");
  await expect(page.locator("body")).not.toContainText("Cannot read properties");
  await expect(page.locator("main").first()).toBeVisible();
}

export async function expectNoDocumentOverflow(page: Page): Promise<void> {
  const metrics = await page.evaluate(() => ({
    vertical: document.documentElement.scrollHeight > document.documentElement.clientHeight + 1,
    horizontal: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  }));
  expect(metrics).toEqual({ vertical: false, horizontal: false });
}

async function routeEnterpriseApi(
  route: Route,
  options: EnterpriseHarnessOptions = {},
): Promise<void> {
  const request = route.request();
  const url = new URL(request.url());
  const path = url.pathname;
  const method = request.method();

  if (path === "/api/auth/me") {
    await fulfillJson(route, authUser);
    return;
  }
  if (path === "/api/terminal/tokens" && method === "POST") {
    const payload = request.postDataJSON() as { terminal_id?: string } | null;
    const terminalId = payload?.terminal_id ?? "terminal";
    await fulfillJson(route, {
      token: `terminal-token-${terminalId}`,
      terminal_id: terminalId,
      expires_at: "2026-07-12T00:00:30Z",
    });
    return;
  }
  if (path === "/api/onboarding/state") {
    await fulfillJson(route, onboardingState);
    return;
  }
  if (path === "/api/agents" && method === "GET") {
    await fulfillJson(route, { items: [agent], next_cursor: null });
    return;
  }
  if (path === "/api/agents" && method === "POST") {
    await fulfillJson(route, agent);
    return;
  }
  if (path === "/api/agents/local-agent/connections") {
    await fulfillJson(route, { items: [] });
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/triggers`) {
    await fulfillJson(route, { items: [] });
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/versions`) {
    await fulfillJson(route, { items: [] });
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/clone` && method === "POST") {
    await fulfillJson(route, {
      ...agent,
      id: `${enterpriseIds.agentId}-clone`,
      name: "默认智能体克隆副本",
    });
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/capabilities/attachments` && method === "POST") {
    await fulfillJson(route, {
      status: "attached",
      attachment_id: "attachment-enterprise",
      agent_id: enterpriseIds.agentId,
      capability_id: "capability-read-file",
      capability_version_id: "capability-version-read-file",
      enabled: true,
      priority: 10,
    });
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/token-optimizer` && method === "POST") {
    await fulfillJson(route, {
      status: "selected",
      preset_id: "balanced",
      attachment_id: "attachment-token-optimizer",
      capability_id: "capability-token-optimizer",
      capability_version_id: "capability-version-token-optimizer",
      enabled: true,
      priority: 20,
    });
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/context/compress` && method === "POST") {
    await fulfillJson(route, workspaceContextCompression);
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}`) {
    await fulfillJson(route, agent);
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources` && method === "POST") {
    await fulfillJson(route, knowledgeSources.items[0]);
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/import` && method === "POST") {
    await fulfillJson(route, knowledgeSources.items[0]);
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources`) {
    await fulfillJson(route, knowledgeSources);
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise` && method === "PATCH") {
    await fulfillJson(route, knowledgeSources.items[0]);
    return;
  }
  if (
    path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise/disable` ||
    path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise/enable` ||
    path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise/archive` ||
    path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise/scope`
  ) {
    await fulfillJson(route, knowledgeSources.items[0]);
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise` && method === "DELETE") {
    await fulfillJson(route, {});
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise/documents`) {
    await fulfillJson(route, method === "POST" ? knowledgeSources.items[0] : [knowledgeDocument]);
    return;
  }
  if (path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise/documents/import` && method === "POST") {
    await fulfillJson(route, knowledgeSources.items[0]);
    return;
  }
  if (
    path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise/documents/${knowledgeDocument.id}/versions` ||
    path === `/api/agents/${enterpriseIds.agentId}/knowledge/sources/knowledge-enterprise/documents/${knowledgeDocument.id}/versions/import`
  ) {
    await fulfillJson(route, knowledgeSources.items[0]);
    return;
  }
  if (path === "/api/agents/token-optimizer/presets") {
    await fulfillJson(route, tokenOptimizerPresets);
    return;
  }
  if (path === "/api/agents/runs") {
    await fulfillJson(route, { items: [taskRun], next_cursor: null });
    return;
  }
  if (path === `/api/agents/runs/${enterpriseIds.runId}/workspace`) {
    await fulfillJson(route, runWorkspace);
    return;
  }
  if (path === `/api/agents/runs/${enterpriseIds.runId}/execute`) {
    await fulfillJson(route, { ...taskRun, status: "RUNNING" });
    return;
  }
  if (path === `/api/agents/runs/${enterpriseIds.runId}/orchestrate`) {
    await fulfillJson(route, { run_id: enterpriseIds.runId, strategy: "enterprise", assignments: [], handoffs: [], message: "orchestrated" });
    return;
  }

  if (path === "/api/tasks" || path === "/api/agents/runs") {
    await fulfillJson(route, { items: [taskRun], next_cursor: null });
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}`) {
    await fulfillJson(route, taskRun);
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/events`) {
    await fulfillJson(route, { items: runWorkspace.events, next_cursor: null });
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/subagents`) {
    await fulfillJson(route, { items: runWorkspace.subagents, next_cursor: null });
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/model-calls`) {
    await fulfillJson(route, { items: runWorkspace.model_calls, next_cursor: null });
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/tool-calls`) {
    await fulfillJson(route, { items: runWorkspace.tool_calls, next_cursor: null });
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/result`) {
    await fulfillJson(route, taskResult);
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/fanout-batches`) {
    await fulfillJson(route, fanoutBatches);
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/subagents/recovery-batches`) {
    await fulfillJson(route, { items: [], next_cursor: null });
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/replay`) {
    await fulfillJson(route, { sequence: 3, status: "ok", state_json: { replayed: true }, replayed_until_sequence: 3 });
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/tool-approvals/appr-enterprise/approve`) {
    await fulfillJson(route, { items: [], next_cursor: null });
    return;
  }
  if (path === `/api/tasks/${enterpriseIds.runId}/tool-approvals/appr-enterprise/reject`) {
    await fulfillJson(route, { items: [], next_cursor: null });
    return;
  }

  if (path === "/api/teams" && method === "POST") {
    await fulfillJson(route, teamForId("team-created"));
    return;
  }
  if (path === "/api/teams" && method === "GET") {
    await fulfillJson(route, { items: [team], next_cursor: null });
    return;
  }
  const teamMatch = path.match(/^\/api\/teams\/([^/]+)(?:\/(.*))?$/);
  if (teamMatch) {
    const requestedTeamId = teamMatch[1];
    const suffix = teamMatch[2] ?? "";
    if (suffix === "") {
      await fulfillJson(route, teamForId(requestedTeamId));
      return;
    }
    if (suffix === "tasks") {
      await fulfillJson(route, method === "POST" ? teamTaskForId(requestedTeamId) : teamForId(requestedTeamId).tasks);
      return;
    }
    if (suffix.startsWith("tasks/")) {
      await fulfillJson(route, teamTaskForId(requestedTeamId));
      return;
    }
    if (suffix === "events") {
      await fulfillJson(route, teamEventsForId(requestedTeamId));
      return;
    }
    if (suffix === "stream") {
      await fulfillSse(route, [
        sseFrame(teamEventsForId(requestedTeamId)[0]),
      ]);
      return;
    }
    if (suffix === "messages") {
      await fulfillJson(route, teamMessageForId(requestedTeamId));
      return;
    }
    if (suffix === "agents" && method === "POST") {
      await fulfillJson(route, teamAgentForId(requestedTeamId, "reviewer"));
      return;
    }
    const agentMatch = suffix.match(/^agents\/([^/]+)(?:\/(.*))?$/);
    if (agentMatch) {
      const slotId = agentMatch[1];
      const agentSuffix = agentMatch[2] ?? "";
      if (agentSuffix === "wake/stream") {
        await fulfillSse(route, [
          namedSseFrame("status", { agent: teamAgentForId(requestedTeamId, slotId) }),
          namedSseFrame("delta", { slot_id: slotId, content: "Team-created subagent evidence is linked." }),
          namedSseFrame("done", { agent: { ...teamAgentForId(requestedTeamId, slotId), status: "idle" }, message: teamMessageForId(requestedTeamId) }),
        ]);
        return;
      }
      if (agentSuffix === "mailbox/read") {
        await fulfillJson(route, [teamMessageForId(requestedTeamId)]);
        return;
      }
      if (agentSuffix === "wake" || agentSuffix === "wake/cancel" || method === "PATCH" || method === "DELETE") {
        await fulfillJson(route, teamAgentForId(requestedTeamId, slotId));
        return;
      }
    }
    if (suffix.startsWith("tools/")) {
      await fulfillJson(route, {
        tool_name: suffix.split("/").pop(),
        from_agent_slot_id: "leader",
        result: `Created enterprise evidence for ${enterpriseIds.subagentId}`,
      });
      return;
    }
  }
  if (path === `/api/teams/${enterpriseIds.teamId}`) {
    await fulfillJson(route, team);
    return;
  }
  if (path === `/api/teams/${enterpriseIds.teamId}/tasks`) {
    await fulfillJson(route, team.tasks);
    return;
  }
  if (path === `/api/teams/${enterpriseIds.teamId}/events`) {
    await fulfillJson(route, teamEvents);
    return;
  }
  if (path === `/api/teams/${enterpriseIds.teamId}/stream`) {
    await fulfillSse(route, [
      sseFrame(teamEvents[0]),
    ]);
    return;
  }
  if (path === `/api/teams/${enterpriseIds.teamId}/messages`) {
    await fulfillJson(route, team.messages[0]);
    return;
  }
  if (path === `/api/teams/${enterpriseIds.teamId}/agents/reviewer/wake/stream`) {
    await fulfillSse(route, [
      namedSseFrame("status", { agent: team.agents[1] }),
      namedSseFrame("delta", { slot_id: "reviewer", content: "Team-created subagent evidence is linked." }),
      namedSseFrame("done", { agent: { ...team.agents[1], status: "idle" }, message: team.messages[0] }),
    ]);
    return;
  }
  if (path.endsWith("/wake") || path.endsWith("/wake/cancel")) {
    await fulfillJson(route, team.agents[1]);
    return;
  }
  if (path.startsWith(`/api/teams/${enterpriseIds.teamId}/tools/`)) {
    await fulfillJson(route, {
      tool_name: path.split("/").pop(),
      from_agent_slot_id: "leader",
      result: `Created enterprise evidence for ${enterpriseIds.subagentId}`,
    });
    return;
  }

  if (path === "/api/subagents") {
    await fulfillJson(route, { items: [subagentListItem], next_cursor: null });
    return;
  }
  if (path === `/api/subagents/${enterpriseIds.subagentId}`) {
    await fulfillJson(route, subagentDetail);
    return;
  }
  if (path === "/api/subagents/subagent-enterprise-security") {
    await fulfillJson(route, securitySubagentDetail);
    return;
  }
  if (path === `/api/subagents/${enterpriseIds.subagentId}/cancel` && method === "POST") {
    await fulfillJson(route, { ...subagentDetail, status: "CANCELLED" });
    return;
  }
  if (path === `/api/subagents/${enterpriseIds.subagentId}/fanout/extend` && method === "POST") {
    await fulfillJson(route, {
      fanout_batch_id: "fanout-enterprise",
      added_count: 1,
      fanout_total: 3,
      extend_count: 1,
      agent_runs: [securitySubagentDetail],
    });
    return;
  }
  if (path === "/api/subagents/bulk" && method === "POST") {
    await fulfillJson(route, { action: "cancel", requested_count: 1, updated_count: 1, items: [{ ...subagentDetail, status: "CANCELLED" }] });
    return;
  }
  if (path === "/api/subagent-specialists") {
    await fulfillJson(route, { items: [specialist], next_cursor: null });
    return;
  }
  if (path === `/api/subagent-specialists/${enterpriseIds.specialistId}`) {
    await fulfillJson(route, specialist);
    return;
  }
  if (path === `/api/subagent-specialists/${enterpriseIds.specialistId}/stats`) {
    await fulfillJson(route, specialistStats);
    return;
  }
  if (path === `/api/subagent-specialists/${enterpriseIds.specialistId}/preflight` && method === "POST") {
    await fulfillJson(route, { valid: true, errors: [], normalized_output: { result: "passed" }, schema_sha256: specialist.output_schema_sha256 });
    return;
  }
  if (path === "/api/subagent-specialists/calibration") {
    await fulfillJson(route, specialistCalibration);
    return;
  }
  if (path === "/api/subagent-marketplace/listings") {
    await fulfillJson(route, { items: [marketplaceListing], next_cursor: null });
    return;
  }
  if (path === `/api/subagent-marketplace/listings/${enterpriseIds.listingId}`) {
    await fulfillJson(route, marketplaceListing);
    return;
  }
  if (path === `/api/subagent-marketplace/listings/${enterpriseIds.listingId}/install` && method === "POST") {
    await fulfillJson(route, specialistMarketplaceInstallation, 201);
    return;
  }
  if (path === "/api/subagents/recovery/summary") {
    await fulfillJson(route, recoverySummary);
    return;
  }
  if (path.startsWith("/api/subagents/recovery/global-summary")) {
    await fulfillJson(route, recoveryGlobalSummary);
    return;
  }

  if (path === "/api/tools/registry") {
    await fulfillJson(route, toolRegistry);
    return;
  }
  if (path === "/api/tools/adapters") {
    await fulfillJson(route, { items: [adapter] });
    return;
  }
  if (path.match(/^\/api\/tools\/adapters\/[^/]+\/health$/)) {
    await fulfillJson(route, adapterHealth);
    return;
  }
  if (path === "/api/tools/mcp-servers") {
    await fulfillJson(route, { items: [mcpServer] });
    return;
  }
  if (path.match(/^\/api\/tools\/mcp-servers\/[^/]+\/discover$/) && method === "POST") {
    await fulfillJson(route, mcpServerDiscoveryPayload());
    return;
  }
  if (path === "/api/tools/capabilities/packages") {
    await fulfillJson(route, { items: [capabilityPackage], next_cursor: null });
    return;
  }
  if (path === "/api/tools/capabilities/admin-validate" && method === "POST") {
    await fulfillJson(route, capabilityValidation);
    return;
  }
  if (path === "/api/tools/capabilities/packages/private" && method === "POST") {
    await fulfillJson(route, { ...capabilityPackage, status: "staged", approved_at: null });
    return;
  }
  if (path === "/api/tools/capabilities/packages/public" && method === "POST") {
    await fulfillJson(route, { ...capabilityPackage, status: "staged", source_kind: "public_url", approved_at: null });
    return;
  }
  if (path.match(/^\/api\/tools\/capabilities\/packages\/[^/]+\/approve$/) && method === "POST") {
    await fulfillJson(route, { ...capabilityPackage, status: "approved", approved_at: now });
    return;
  }
  if (path.match(/^\/api\/tools\/capabilities\/packages\/[^/]+\/attachments$/) && method === "POST") {
    await fulfillJson(route, capabilityAttachment, 201);
    return;
  }
  if (path.match(/^\/api\/tools\/capabilities\/packages\/[^/]+\/rollback$/) && method === "POST") {
    await fulfillJson(route, { ...capabilityPackage, updated_at: now });
    return;
  }
  if (path.match(/^\/api\/tools\/capabilities\/packages\/[^/]+\/uninstall$/) && method === "POST") {
    await fulfillJson(route, { ...capabilityPackage, status: "uninstalled", updated_at: now });
    return;
  }
  if (path.match(/^\/api\/tools\/capabilities\/attachments\/[^/]+$/) && method === "PATCH") {
    await fulfillJson(route, capabilityAttachment);
    return;
  }
  if (path.match(/^\/api\/tools\/capabilities\/staged\/[^/]+\/enable$/) && method === "POST") {
    await fulfillJson(route, capabilityInstallResponse("ready"));
    return;
  }
  if (path === "/api/tools/capabilities/dependency-preflight") {
    await fulfillJson(route, dependencyPreflight);
    return;
  }
  if (path === "/api/tools/capabilities/marketplace") {
    await fulfillJson(route, capabilityMarketplace);
    return;
  }
  if (path === "/api/tools/capabilities/preflight/marketplace" && method === "POST") {
    await fulfillJson(route, capabilityInstallResponse("staged"));
    return;
  }
  if (path === "/api/tools/capabilities/preflight/public-url" && method === "POST") {
    await fulfillJson(route, capabilityInstallResponse("staged"));
    return;
  }
  if (
    (path === "/api/tools/capabilities/install/trusted-url" ||
      path === "/api/tools/capabilities/install/upload") &&
    method === "POST"
  ) {
    await fulfillJson(route, capabilityInstallResponse("attached"));
    return;
  }
  if (path === "/api/tools/capabilities/test-invoke" && method === "POST") {
    await fulfillJson(route, toolExecuteResult);
    return;
  }
  if (path === "/api/tools/capabilities/runtime-configs") {
    await fulfillJson(route, { items: [capabilityRuntimeConfig] });
    return;
  }
  if (path === "/api/tools/capabilities/runtime-config") {
    await fulfillJson(route, capabilityRuntimeConfig);
    return;
  }
  if (path.startsWith("/api/tools/capabilities/runtime-config/")) {
    await fulfillJson(route, capabilityRuntimeConfig);
    return;
  }

  if (path === "/api/settings/models") {
    await fulfillJson(route, modelSettings);
    return;
  }
  if (path === "/api/settings/models/health") {
    await fulfillJson(route, modelHealth);
    return;
  }
  if (path === "/api/settings/models/fallbacks") {
    await fulfillJson(route, modelFallbacks);
    return;
  }
  if (path === "/api/settings/models/pricing-sources") {
    if (options.missingModelPricingSources) {
      await fulfillJson(route, { detail: "Not Found" }, 404);
      return;
    }
    await fulfillJson(route, modelPricingSources);
    return;
  }
  if (path === "/api/settings/policies") {
    await fulfillJson(route, policySettings);
    return;
  }
  if (path === "/api/secrets") {
    await fulfillJson(route, { items: [] });
    return;
  }
  if (path === "/api/plugins/marketplace") {
    await fulfillJson(route, { installed_count: 0, items: [] });
    return;
  }
  if (path === "/api/plugins/prompt-templates") {
    await fulfillJson(route, { items: [] });
    return;
  }
  if (path === "/api/users" && method === "POST") {
    await fulfillJson(route, { ...userMember, user_id: "invited-enterprise", email: "invited@dev.local", status: "invited", accepted_at: null });
    return;
  }
  if (path === "/api/users") {
    await fulfillJson(route, [userMember]);
    return;
  }
  if (path === "/api/users/dev-engineer/role" && method === "PATCH") {
    await fulfillJson(route, { ...userMember, role: "member" });
    return;
  }
  if (path === "/api/users/dev-engineer" && method === "DELETE") {
    await fulfillJson(route, {});
    return;
  }
  if (path === "/api/api-keys" && method === "POST") {
    await fulfillJson(route, { ...apiKey, id: "apikey-created-enterprise", key: "hk_live_created_enterprise_secret" }, 201);
    return;
  }
  if (path === "/api/api-keys") {
    await fulfillJson(route, [apiKey]);
    return;
  }
  if (path === "/api/api-keys/apikey-enterprise" && method === "DELETE") {
    await fulfillJson(route, {});
    return;
  }
  if (path === "/api/audit") {
    await fulfillJson(route, { items: [auditEvent], next_cursor: null });
    return;
  }
  if (path === "/api/audit/export.csv") {
    await fulfillCsv(route, "created_at,actor_id,action\n2026-05-30T06:33:42.000Z,dev-engineer,team.subagent.projected\n");
    return;
  }
  if (path === "/api/retention/policies") {
    await fulfillJson(route, { items: [retentionPolicy] });
    return;
  }
  if (path === "/api/retention/policies/retention-enterprise" && method === "PATCH") {
    await fulfillJson(route, retentionPolicy);
    return;
  }
  if (path === "/api/retention/run" && method === "POST") {
    await fulfillJson(route, { items: [retentionRun] });
    return;
  }
  if (path === "/api/retention/runs") {
    await fulfillJson(route, { items: [retentionRun] });
    return;
  }
  if (path === `/api/organizations/${enterpriseIds.orgId}/exports`) {
    await fulfillJson(route, { items: [dataExport] });
    return;
  }
  if (path === `/api/organizations/${enterpriseIds.orgId}/export`) {
    await fulfillJson(route, dataExport);
    return;
  }
  if (path === `/api/organizations/${enterpriseIds.orgId}/dry-run` && method === "DELETE") {
    await fulfillJson(route, {
      organization_id: enterpriseIds.orgId,
      organization_name: "Dev Workspace",
      counts: { tasks: 1 },
      confirmation_name: "Dev Workspace",
    });
    return;
  }
  if (path === `/api/organizations/${enterpriseIds.orgId}` && method === "DELETE") {
    await fulfillJson(route, {
      organization_id: enterpriseIds.orgId,
      status: "deleted",
      deleted_counts_json: { tasks: 1 },
    });
    return;
  }
  if (path === "/api/frontend-errors") {
    await fulfillJson(route, { items: [frontendError], next_cursor: null });
    return;
  }
  if (path === "/api/frontend-errors/summary") {
    await fulfillJson(route, { items: [frontendErrorSummary] });
    return;
  }

  if (path === "/api/sandboxes/warm-pool") {
    await fulfillJson(route, warmPool);
    return;
  }
  if (path === "/api/sandboxes/quota/usage") {
    await fulfillJson(route, sandboxQuotaUsage);
    return;
  }
  if (path === "/api/sandboxes/quota/history") {
    await fulfillJson(route, { items: [sandboxQuotaHistory], next_cursor: null });
    return;
  }
  if (path === "/api/sandboxes/warm-pool/benchmarks") {
    await fulfillJson(route, { items: [warmPoolBenchmark], next_cursor: null });
    return;
  }
  if (path === "/api/sandboxes/warm-pool/benchmark" && method === "POST") {
    await fulfillJson(route, warmPoolBenchmark);
    return;
  }

  if (path === "/api/observability/summary") {
    await fulfillJson(route, observabilitySummary);
    return;
  }
  if (path === "/api/observability/architecture") {
    await fulfillJson(route, {
      planner_executor: {
        enabled: true,
        planner: "planner",
        executor: "dag",
        react_engine: "harness",
        planner_prompt_version: "planner-v1",
        plan_total: 7,
        sync_step_total: 11,
        async_step_total: 13,
        langgraph_step_total: 42,
        status: "active",
      },
      event_sourcing: {
        enabled: true,
        event_total: 100,
        snapshot_total: 1,
        snapshot_frequency_events: 25,
        replay_enabled: true,
        resume_enabled: true,
        audit_log_enabled: true,
        time_travel_debugging_enabled: true,
        last_sequence: 99,
      },
      notes: ["langgraph_workflow is not a ToolRunner tool"],
    });
    return;
  }
  if (path === "/api/observability/token-savings") {
    await fulfillJson(route, tokenSavings);
    return;
  }
  if (path === "/api/observability/cost-rollup") {
    await fulfillJson(route, costRollup);
    return;
  }
  if (path === "/api/observability/grounding-quality") {
    await fulfillJson(route, groundingQuality);
    return;
  }
  if (path === "/api/observability/logs") {
    await fulfillJson(route, { items: [logLine], next_cursor: null });
    return;
  }
  if (path === "/api/observability/traces") {
    await fulfillJson(route, { items: [traceListItem], next_cursor: null });
    return;
  }
  if (path === `/api/observability/traces/${enterpriseIds.traceId}`) {
    await fulfillJson(route, traceDetail);
    return;
  }
  if (path === "/api/observability/alert-rules" && method === "POST") {
    await fulfillJson(route, { ...alertRule, id: "alert-created-enterprise", name: "Created Cost Gate" }, 201);
    return;
  }
  if (path === "/api/observability/alert-rules") {
    await fulfillJson(route, { items: [alertRule], next_cursor: null });
    return;
  }
  if (path === `/api/observability/alert-rules/${enterpriseIds.alertRuleId}` && method === "PATCH") {
    await fulfillJson(route, { ...alertRule, updated_at: now });
    return;
  }
  if (path === `/api/observability/alert-rules/${enterpriseIds.alertRuleId}` && method === "DELETE") {
    await fulfillJson(route, {});
    return;
  }
  if (path === "/api/observability/alert-events") {
    await fulfillJson(route, { items: [alertEvent], next_cursor: null });
    return;
  }
  if (path === "/api/observability/alert-rules/evaluate") {
    await fulfillJson(route, { items: [alertEvent], next_cursor: null });
    return;
  }
  if (path === "/api/observability/notification-channels" && method === "POST") {
    await fulfillJson(route, { ...notificationChannel, id: "channel-created-enterprise", name: "Created Webhook" }, 201);
    return;
  }
  if (path === "/api/observability/notification-channels") {
    await fulfillJson(route, { items: [notificationChannel], next_cursor: null });
    return;
  }
  if (path === "/api/observability/notification-channels/channel-enterprise" && method === "PATCH") {
    await fulfillJson(route, { ...notificationChannel, updated_at: now });
    return;
  }
  if (path === "/api/observability/notification-channels/channel-enterprise" && method === "DELETE") {
    await fulfillJson(route, {});
    return;
  }
  if (path === "/api/observability/grafana/dashboards") {
    await fulfillJson(route, { items: [{ uid: "dash-enterprise", title: "Agent Overview", url: "http://grafana/d/agent", source: "grafana" }] });
    return;
  }
  if (path === "/api/observability/services/health") {
    await fulfillJson(route, { services: [{ name: "otel-collector", status: "healthy", latency_ms: 8, alert_status: "ok", alert_severity: null }] });
    return;
  }
  if (path === "/api/observability/exports" || path === "/api/observability/exports/history") {
    await fulfillJson(route, { items: [] });
    return;
  }

  if (path === "/api/evals/datasets" && method === "POST") {
    await fulfillJson(route, { ...evalDataset, id: "dataset-created-enterprise", name: "Created Dataset" }, 201);
    return;
  }
  if (path === "/api/evals/datasets") {
    await fulfillJson(route, { items: [evalDataset], next_cursor: null });
    return;
  }
  if (path === `/api/evals/datasets/${evalDataset.id}/cases/from-run/${enterpriseIds.runId}` && method === "POST") {
    await fulfillJson(route, evalCase, 201);
    return;
  }
  if (path === `/api/evals/datasets/${evalDataset.id}/runs` && method === "POST") {
    await fulfillJson(route, evalRun, 201);
    return;
  }
  if (path === `/api/evals/datasets/${evalDataset.id}/baseline` && method === "PATCH") {
    await fulfillJson(route, { ...evalDataset, baseline_run_id: enterpriseIds.evalRunId });
    return;
  }
  if (path.match(/^\/api\/evals\/datasets\/[^/]+\/cases$/)) {
    await fulfillJson(route, { items: [evalCase], next_cursor: null });
    return;
  }
  if (path.match(/^\/api\/evals\/datasets\/[^/]+\/cases\/from-run\/[^/]+$/) && method === "POST") {
    await fulfillJson(route, evalCase, 201);
    return;
  }
  if (path.match(/^\/api\/evals\/datasets\/[^/]+\/runs$/) && method === "POST") {
    await fulfillJson(route, evalRun, 201);
    return;
  }
  if (path.match(/^\/api\/evals\/datasets\/[^/]+\/baseline$/) && method === "PATCH") {
    await fulfillJson(route, { ...evalDataset, baseline_run_id: enterpriseIds.evalRunId });
    return;
  }
  if (path === "/api/evals/runs") {
    await fulfillJson(route, { items: [evalRun], next_cursor: null });
    return;
  }
  if (path === "/api/evals/results/pending-review") {
    await fulfillJson(route, []);
    return;
  }
  if (path === "/api/evals/experiments") {
    await fulfillJson(route, { items: [], next_cursor: null });
    return;
  }
  if (path === `/api/evals/runs/${enterpriseIds.evalRunId}/regression`) {
    await fulfillJson(route, regressionDelta);
    return;
  }
  if (path === `/api/evals/runs/${enterpriseIds.evalRunId}`) {
    await fulfillJson(route, evalRun);
    return;
  }

  await route.fulfill({
    status: 404,
    contentType: "application/json",
    body: JSON.stringify({
      detail: `Unhandled e2e API route: ${method} ${path}${url.search}`,
    }),
  });
}

async function fulfillJson(route: Route, payload: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

async function fulfillCsv(route: Route, body: string): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "text/csv",
    headers: { "content-disposition": 'attachment; filename="audit-events.csv"' },
    body,
  });
}

async function fulfillSse(route: Route, frames: string[]): Promise<void> {
  await route.fulfill({
    status: 200,
    contentType: "text/event-stream",
    body: frames.join(""),
  });
}

function sseFrame(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

function namedSseFrame(event: string, payload: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

function teamForId(teamId: string) {
  return {
    ...team,
    id: teamId,
    agents: team.agents.map((agent) => ({ ...agent, team_id: teamId })),
    messages: team.messages.map((message) => ({ ...message, team_id: teamId })),
    tasks: team.tasks.map((task) => ({ ...task, team_id: teamId })),
  };
}

function teamAgentForId(teamId: string, slotId: string) {
  const base = team.agents.find((agent) => agent.slot_id === slotId) ?? team.agents[1];
  return {
    ...base,
    id: `team-agent-${slotId}`,
    team_id: teamId,
    slot_id: slotId,
    agent_name: slotId === "leader" ? "Default Agent" : "Review Agent",
  };
}

function teamMessageForId(teamId: string) {
  return {
    ...team.messages[0],
    id: `team-message-${teamId}`,
    team_id: teamId,
  };
}

function teamTaskForId(teamId: string) {
  return {
    ...team.tasks[0],
    id: `team-task-${teamId}`,
    team_id: teamId,
  };
}

function teamEventsForId(teamId: string) {
  return teamEvents.map((event) => ({ ...event, id: `${event.id}-${teamId}`, team_id: teamId }));
}

function capabilityInstallResponse(readyState: "attached" | "ready" | "staged") {
  return {
    package: readyState === "staged" ? { ...capabilityPackage, status: "staged", approved_at: null } : capabilityPackage,
    validation_summary: { status: "valid", source_resolution: "registry_metadata_only_no_url_fetch" },
    ready_state: readyState,
    next_step_label: readyState === "attached" ? "Open Agent attachment" : readyState === "ready" ? "Attach to Agent" : "Approve marketplace version",
    staged_capability_id: readyState === "staged" ? capabilityPackage.id : null,
    capability_id: readyState === "staged" ? null : capabilityPackage.capability_id,
    capability_version_id: readyState === "staged" ? null : capabilityPackage.capability_version_id,
    attachment: readyState === "attached" ? capabilityAttachment : null,
  };
}

const authUser = {
  user_id: "dev-engineer",
  email: "engineer@dev.local",
  name: "Dev Engineer",
  organization_id: enterpriseIds.orgId,
  role: "admin",
  permissions: ["*"],
  organizations: [{ id: enterpriseIds.orgId, name: "Dev Workspace", slug: "dev-org", role: "admin" }],
};

const onboardingState = {
  id: "onboarding-enterprise",
  organization_id: enterpriseIds.orgId,
  user_id: "dev-engineer",
  current_step: 3,
  completed: true,
  skipped: false,
  demo_loaded: true,
  provider_json: {},
  agent_id: enterpriseIds.agentId,
  demo_task_id: enterpriseIds.runId,
  created_at: now,
  updated_at: now,
  completed_at: now,
};

const agent = {
  id: enterpriseIds.agentId,
  name: "Default Agent",
  description: "Enterprise delivery agent",
  role: "engineer",
  status: "active",
  model_provider: "deepseek-flash",
  model_name: "deepseek-v4-flash",
  system_prompt: "Operate with Harness evidence.",
  tools_json: ["read_file", "github_search"],
  routing_tags: ["enterprise"],
  max_parallel_assignments: 2,
  created_at: now,
  updated_at: now,
};

const taskRun = {
  id: enterpriseIds.runId,
  title: "Validate Enterprise Harness Chain",
  goal: "Models, tools, knowledge, subagents, teams, evals, and observability stay linked.",
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
};

const runWorkspace = {
  run: taskRun,
  token_optimization: {},
  assignments: [],
  handoffs: [],
  plan: {
    id: "plan-enterprise",
    task_id: enterpriseIds.runId,
    version: 1,
    status: "COMPLETED",
    summary: "Validate chain",
    planner_source: "deepseek-v4-flash",
    planner_attempts: 1,
    planner_prompt_version: "v2",
    quality_score: 0.98,
    validation_warnings: [],
    quality_gates: { coverage: true },
    plan_json: {},
    steps: [],
    created_at: now,
  },
  events: [
    { id: "evt-enterprise-1", task_id: enterpriseIds.runId, agent_run_id: enterpriseIds.runId, sequence: 1, event_type: "PLAN_CREATED", payload_json: { message: "计划已创建" }, actor_type: "system", actor_id: null, trace_id: enterpriseIds.traceId, created_at: now },
  ],
  knowledge_grounding: {
    retrieval_session: { id: "retrieval-enterprise", query: "enterprise chain", mode: "local", local_status: "sufficient", vector_capability: "available", strategy: "vector", min_hits: 2, min_score: 0.6, max_local_chunks: 6, max_web_results: 0, metadata_json: {}, created_at: now },
    retrieval_hits: [],
    citations: [],
    prompt_manifest: null,
    policy_audits: [],
    web_sources: [],
    vector_capability: "available",
    local_status: "sufficient",
    grounded: true,
    grounding_provider: "local_knowledge",
    fixture_grounded: false,
    verified_grounded: true,
    grounding_verification_reason: "local_evidence_sufficient",
    evidence_summary: "Knowledge source grounded the enterprise chain.",
    inferred_fallback: false,
    fallback_reason: null,
    selected_retrieval_session_id: "retrieval-enterprise",
    selected_prompt_manifest_id: null,
  },
  subagents: [
    {
      id: enterpriseIds.subagentId,
      task_id: enterpriseIds.runId,
      parent_agent_id: enterpriseIds.agentId,
      agent_type: "subagent",
      status: "SUCCESS",
      context_json: { source: "team_mode_enterprise_projection", team_id: enterpriseIds.teamId, label: "Team release reviewer", step_key: "review-release-chain", fanout_batch_id: "fanout-enterprise" },
      started_at: now,
      completed_at: now,
      timeout_at: null,
      specialist_id: enterpriseIds.specialistId,
      fanout_batch_id: "fanout-enterprise",
      fanout_index: 0,
      fanout_total: 2,
      dynamic_fanout_origin: null,
      dynamic_fanout_requested_by: null,
      dynamic_fanout_reason: null,
      specialist: {
        id: enterpriseIds.specialistId,
        slug: "code-reviewer",
        role: "reviewer",
        display_name: "代码审查专家",
      },
      output: {
        id: "subagent-output-enterprise",
        agent_run_id: enterpriseIds.subagentId,
        task_id: enterpriseIds.runId,
        specialist_id: enterpriseIds.specialistId,
        output_json: { result: "passed", summary: "Team bridge output" },
        output_schema_sha256: "c".repeat(64),
        budget_consumed_json: { cost_usd: "0.000280", prompt_tokens: 1000, completion_tokens: 500 },
        budget_exceeded_json: [],
        written_at: now,
      },
    },
  ],
  tool_calls: [
    { id: "toolcall-enterprise", task_id: enterpriseIds.runId, agent_run_id: enterpriseIds.runId, trace_id: enterpriseIds.traceId, tool_name: "read_file", status: "COMPLETED", risk_level: "low", requires_sandbox: false, sandbox_id: null, duration_ms: 20, input_json: { path: "README.md" }, output_json: { content: "Harness" }, output_kind: "text", output_summary: "Read README", timeout_category: null, error_message: null, created_at: now },
  ],
  model_calls: [
    {
      id: "modelcall-enterprise",
      task_id: enterpriseIds.runId,
      agent_run_id: enterpriseIds.runId,
      trace_id: enterpriseIds.traceId,
      model_provider: "deepseek-flash",
      model_name: "deepseek-v4-flash",
      status: "COMPLETED",
      prompt_tokens: 1000,
      completion_tokens: 500,
      duration_ms: 400,
      grounding_correlation_id: "retrieval-enterprise",
      prompt_manifest_id: null,
      model_request_sha256: "a".repeat(64),
      model_request_hash_schema_version: 2,
      context_manifest_id: null,
      request_message_hashes_json: [],
      request_message_hashes_sha256: null,
      hash_recomputability_status: "verified",
      attempt_index: 1,
      terminal_status: "success",
      error_message: null,
      request_json: {},
      response_json: { content: "Enterprise chain complete." },
      created_at: now,
    },
  ],
  approvals: [{ id: "appr-enterprise", task_id: enterpriseIds.runId, tool_call_id: "toolcall-enterprise", status: "PENDING", risk_level: "high", reason: "release gate", requested_by: "system", decided_by: null, decided_at: null, created_at: now }],
  artifacts: [],
  context_assembly: null,
};

const team = {
  id: enterpriseIds.teamId,
  organization_id: enterpriseIds.orgId,
  name: "Enterprise Team",
  status: "ACTIVE",
  workspace: "/tmp/enterprise-team",
  workspace_mode: "shared",
  leader_slot_id: "leader",
  created_by: "dev-engineer",
  agents: [
    { id: "team-agent-leader", team_id: enterpriseIds.teamId, slot_id: "leader", agent_id: enterpriseIds.agentId, role: "leader", agent_name: "Default Agent", status: "idle", model_provider: "deepseek-flash", model_name: "deepseek-v4-flash", conversation_id: "session-leader", session_id: "session-leader", session_messages: [], metadata_json: {}, created_at: now, updated_at: now },
    { id: "team-agent-reviewer", team_id: enterpriseIds.teamId, slot_id: "reviewer", agent_id: enterpriseIds.agentId, role: "teammate", agent_name: "Review Agent", status: "completed", model_provider: "deepseek-flash", model_name: "deepseek-v4-flash", conversation_id: "session-reviewer", session_id: "session-reviewer", session_messages: [], metadata_json: { specialist_id: enterpriseIds.specialistId }, created_at: now, updated_at: now },
  ],
  messages: [{ id: "team-message-1", team_id: enterpriseIds.teamId, to_agent_slot_id: "leader", from_agent_slot_id: "reviewer", type: "assistant", content: "Team-created subagent evidence is linked.", summary: null, read: true, files_json: [], metadata_json: { subagent_id: enterpriseIds.subagentId }, created_at: now }],
  tasks: [{ id: "team-task-enterprise", team_id: enterpriseIds.teamId, subject: "Review release chain", description: "审查企业交付链路。", owner_slot_id: "reviewer", status: "completed", blocked_by_json: [], blocks_json: [], metadata_json: { enterprise_projection: { run_id: enterpriseIds.runId, subagent_id: enterpriseIds.subagentId, specialist_id: enterpriseIds.specialistId } }, created_at: now, updated_at: now }],
  unread_counts: {},
  team_tools: ["team_spawn_agent", "team_task_create", "team_send_message"],
  created_at: now,
  updated_at: now,
};

const teamEvents = [{ id: "team-event-1", team_id: enterpriseIds.teamId, sequence: 1, event_type: "TEAM_TASK_CREATED", payload_json: { subagent_id: enterpriseIds.subagentId }, actor_type: "system", actor_id: null, created_at: now }];

const subagentListItem = {
  id: enterpriseIds.subagentId,
  task_id: enterpriseIds.runId,
  parent_agent_id: enterpriseIds.agentId,
  agent_type: "subagent",
  status: "SUCCESS",
  specialist_id: enterpriseIds.specialistId,
  context_json: { source: "team_mode_enterprise_projection", team_id: enterpriseIds.teamId, label: "Team release reviewer", step_key: "review-release-chain" },
  started_at: now,
  completed_at: now,
  timeout_at: null,
  fanout_batch_id: "fanout-enterprise",
  fanout_index: 0,
  fanout_total: 2,
  dynamic_fanout_origin: null,
  dynamic_fanout_requested_by: null,
  dynamic_fanout_reason: null,
  specialist: null,
  specialist_slug: "code-reviewer",
};
const subagentDetail = { ...subagentListItem, output: { id: "subagent-output-enterprise", agent_run_id: enterpriseIds.subagentId, task_id: enterpriseIds.runId, specialist_id: enterpriseIds.specialistId, output_json: { result: "passed", summary: "Team bridge output" }, output_schema_sha256: "c".repeat(64), budget_consumed_json: { cost_usd: "0.000280", prompt_tokens: 1000, completion_tokens: 500 }, budget_exceeded_json: [], written_at: now } };
const securitySubagentDetail = {
  ...subagentDetail,
  id: "subagent-enterprise-security",
  status: "RUNNING",
  specialist_id: null,
  specialist_slug: "safety-checker",
  output: null,
  fanout_index: 1,
  dynamic_fanout_origin: "fanout-enterprise",
  dynamic_fanout_requested_by: enterpriseIds.subagentId,
  dynamic_fanout_reason: "enterprise_risk_review",
};
const specialist = {
  id: enterpriseIds.specialistId,
  organization_id: enterpriseIds.orgId,
  slug: "code-reviewer",
  display_name: "代码审查专家",
  description: "Review code",
  role: "reviewer",
  system_prompt: "review",
  capability_slugs_json: [],
  output_schema_json: { type: "object" },
  output_schema_sha256: "f".repeat(64),
  budget_json: { max_tool_calls: 8, max_runtime_seconds: 120, max_cost_usd: "0.010000" },
  trigger_keywords_json: ["review"],
  visibility: "org",
  status: "ACTIVE",
  created_by: "dev-engineer",
  created_at: now,
  updated_at: now,
};
const specialistStats = {
  specialist_id: enterpriseIds.specialistId,
  slug: "code-reviewer",
  window: "30d",
  total_invocations: 3,
  success_count: 3,
  failed_count: 0,
  budget_exceeded_count: 0,
  depth_rejected_count: 0,
  success_rate: 1,
  avg_runtime_ms: 120,
  p95_runtime_ms: 180,
  avg_cost_usd: "0.001000",
  total_cost_usd: "0.003000",
  avg_tool_calls: 1,
  avg_output_size_bytes: 256,
  recent_failure_reasons: [],
};
const specialistCalibration = {
  organization_id: enterpriseIds.orgId,
  window: "30d",
  decision_count: 1,
  low_sample: false,
  ece: 0,
  buckets: [
    {
      bucket: "0.9-1.0",
      min_confidence: 0.9,
      max_confidence: 1,
      decision_count: 1,
      success_count: 1,
      success_rate: 1,
      avg_confidence: 0.98,
      ece_contribution: 0,
    },
  ],
};
const marketplaceListing = {
  id: enterpriseIds.listingId,
  slug: "enterprise-reviewer",
  display_name: "Enterprise Reviewer",
  description: "Verified reviewer for Harness enterprise delivery chains.",
  author_org_id: enterpriseIds.orgId,
  author_name: "Harness",
  version: "1.0.0",
  manifest_json: { status: "verified", specialist_slug: "code-reviewer", tags: ["enterprise"] },
  signature: `hmac-sha256:${"a".repeat(64)}`,
  verified: true,
  download_count: 1,
  installed: false,
  installed_specialist_id: null,
  created_at: now,
  updated_at: now,
};
const specialistMarketplaceInstallation = {
  id: "installation-enterprise",
  listing_id: enterpriseIds.listingId,
  installed_org_id: enterpriseIds.orgId,
  installed_specialist_id: enterpriseIds.specialistId,
  installed_version: marketplaceListing.version,
  auto_update_enabled: false,
  installed_at: now,
  specialist,
};

const knowledgeDocument = {
  id: "knowledge-document-enterprise",
  source_id: "knowledge-enterprise",
  organization_id: enterpriseIds.orgId,
  agent_id: enterpriseIds.agentId,
  title: "Release Grounding",
  uri: null,
  content_sha256: "b".repeat(64),
  mime_type: "text/markdown",
  status: "INDEXED",
  version: 1,
  logical_document_id: "release-grounding",
  supersedes_document_id: null,
  superseded_at: null,
  ingestion_error: null,
  metadata_json: { route: "/knowledge" },
  idempotency_key: "knowledge-document-enterprise",
  created_by: "dev-engineer",
  created_at: now,
  updated_at: now,
  indexed_at: now,
  chunk_count: 3,
};
const knowledgeSources = {
  items: [
    {
      id: "knowledge-enterprise",
      organization_id: enterpriseIds.orgId,
      agent_id: enterpriseIds.agentId,
      name: "Enterprise Knowledge",
      description: "Grounds release checks",
      source_type: "document",
      status: "INDEXED",
      version: 1,
      scope: "agent",
      expires_at: null,
      disabled_at: null,
      archived_at: null,
      last_indexed_at: now,
      last_ingestion_error: null,
      health_status: "healthy",
      connector_provider: "uploaded_file",
      connector_release_state: "usable",
      connector_counts_toward_complete_usable: true,
      connector_validation_status: "ready",
      connector_validation_messages: [],
      connector_secret_configured: false,
      settings_json: { connector_provider: "uploaded_file" },
      metadata_json: { title: "Release Grounding" },
      idempotency_key: "knowledge-enterprise",
      created_by: "dev-engineer",
      created_at: now,
      updated_at: now,
      latest_documents: [knowledgeDocument],
    },
  ],
  next_cursor: null,
};
const tokenOptimizerPresets = {
  items: [
    { preset_id: "off", display_name: "Off", description: "No token optimization.", enabled: true, priority: 0 },
    { preset_id: "balanced", display_name: "Balanced", description: "Default optimizer.", enabled: true, priority: 20 },
  ],
};

const workspaceContextCompression = {
  status: "ok",
  cache_status: "recomputed",
  summary: "enterprise context summary",
  coverage_node_ids: ["team-message-1"],
  coverage_path_hash: "context-path-enterprise",
  last_covered_node_id: "team-message-1",
  summary_schema_version: "context-summary.v1",
  compression_prompt_version: "context-compression.v1",
  compressor_provider: "deepseek-flash",
  compressor_model: "deepseek-v4-flash",
  estimated_original_tokens: 100,
  estimated_summary_tokens: 24,
  estimated_uncovered_tokens: 0,
  created_at: now,
  updated_at: now,
  error: null,
};
const toolRegistry = { items: [{ name: "read_file", description: "Read a file", category: "filesystem", source: "builtin", risk_level: "low", requires_sandbox: false, network_policy: "none", timeout_seconds: 30, allowed_roles: ["engineer"], audit_level: "standard", idempotent: true, input_schema: { type: "object", properties: { path: { type: "string" } } }, mcp_server: null, mcp_method: null }], categories: ["filesystem"], sources: ["builtin"] };
const adapter = {
  slug: "read_file",
  server_label: "filesystem",
  method: "read_file",
  description: "Read a file",
  version: "1.0.0",
  adapter_module: "harness.adapters.filesystem",
  adapter_sha256: "a".repeat(64),
  input_schema_sha256: "b".repeat(64),
  output_schema_sha256: "c".repeat(64),
  input_schema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
  output_schema: { type: "object", properties: { content: { type: "string" } } },
  requires_secret: false,
  risk_level: "low",
};
const adapterHealth = {
  slug: adapter.slug,
  ok: true,
  latency_ms: 8,
  message: "adapter ready",
  sample: { path: "README.md" },
  last_checked_at: now,
};
const mcpDiscoveredTool = {
  name: "read_file",
  slug: "mcp.filesystem.read_file",
  description: "Read a file through MCP discovery.",
  input_schema: { type: "object", properties: { path: { type: "string" } } },
  annotations: { readOnlyHint: true },
  risk_level: "low",
};
const mcpServer = {
  agent_id: enterpriseIds.agentId,
  tool_name: "read_file",
  server_slug: "filesystem",
  transport: "http",
  configured: true,
  discovery_status: "ready",
  discovery_message: "1 child tool registered",
  discovered_tools: [mcpDiscoveredTool],
  resources_count: 0,
  child_tool_count: 1,
};
const dependencyPreflight = { local_release_path: "1 需要隔离", checks: [{ name: "sandbox-policy", status: "ok" }] };
const capabilityValidation = {
  status: "valid",
  schema_version: 1,
  content_sha256: "f".repeat(64),
  config_sha256: "e".repeat(64),
  errors: [],
  warnings: [],
  risk_score: 1,
  approval_required: false,
  validation_mode: "manifest_only_no_execution",
  source_policy: { allowed: true },
  manifest_summary: { package_type: "tool_definition", permissions: ["filesystem:read"] },
  redacted_payload: { manifest: "redacted" },
  validation: { checks: ["schema", "policy"] },
};
const capabilityPackage = {
  id: "capability-enterprise",
  organization_id: enterpriseIds.orgId,
  package_key: "enterprise/read-file",
  package_type: "tool_definition",
  source_kind: "marketplace_preflight",
  source_uri: "marketplace://enterprise/read-file",
  source_sha256: "d".repeat(64),
  pinned_ref: "marketplace-sha256:enterprise",
  status: "approved",
  risk_level: "low",
  manifest_json: {
    name: "read_file",
    display_name: "Enterprise Read File",
    description: "Filesystem read",
    tools: [{ name: "read_file" }],
  },
  validation_json: { valid: true, checks: ["schema", "policy"] },
  provenance_json: { marketplace_source: "enterprise_fixture" },
  audit_json: { approved_by: "dev-engineer" },
  capability_id: "capability-read-file",
  capability_version_id: "capability-version-read-file",
  created_at: now,
  updated_at: now,
  approved_at: now,
};
const capabilityAttachment = {
  attachment_id: "attachment-enterprise",
  agent_id: enterpriseIds.agentId,
  capability_id: "capability-read-file",
  capability_version_id: "capability-version-read-file",
  enabled: true,
  priority: 10,
};
const capabilityMarketplace = {
  kind: "all",
  query: "",
  items: [
    {
      id: "enterprise-marketplace::read-file@1.0.0",
      kind: "mcp",
      source: "enterprise_fixture",
      source_label: "Enterprise Registry",
      name: "read_file",
      display_name: "Enterprise Read File",
      description: "Verified filesystem read capability for release evidence.",
      categories: ["filesystem", "enterprise"],
      verified: true,
      stars: null,
      use_count: 1,
      quality_score: 0.99,
      latest_version: "1.0.0",
      updated_at: now,
      homepage_url: "https://example.com/enterprise/read-file",
      repository_url: "https://example.com/enterprise/read-file.git",
      remote_url: "https://example.com/mcp/read-file",
      package_type: "tool_definition",
      install_mode: "marketplace_preflight",
      install_label: "登记预检",
      install_payload: {
        source_uri: "marketplace://enterprise/read-file",
        pinned_ref: "marketplace-sha256:enterprise",
        package_type: "tool_definition",
        display_name: "Enterprise Read File",
        description: "Verified filesystem read capability for release evidence.",
        marketplace_source: "enterprise_fixture",
        marketplace_item_id: "enterprise-marketplace::read-file@1.0.0",
        permissions: ["filesystem:read"],
      },
      badges: ["verified", "remote"],
      risk_notes: ["Read-only fixture capability."],
      metadata: { tool_name: "read_file" },
    },
  ],
  sources: [{ id: "enterprise_fixture", label: "enterprise_fixture", status: "ready", item_count: 1, url: "marketplace://enterprise" }],
  errors: [],
};
const capabilityRuntimeConfig = {
  agent_id: enterpriseIds.agentId,
  tool_name: "read_file",
  tool_description: "Read a file",
  source: "builtin",
  capability_id: "capability-read-file",
  capability_version_id: "capability-version-read-file",
  capability_config_sha256: "e".repeat(64),
  attachment_id: "attachment-enterprise",
  attachment_enabled: true,
  configured: true,
  missing_fields: [],
  transport: "http",
  endpoint_url: "https://example.com/mcp/read-file",
  command: null,
  args: [],
  secret_ref: "HARNESS_READ_FILE_TOKEN",
  secret_configured: true,
  timeout_seconds: 30,
  config_json: {},
  registry_visible: true,
  test_input_json: { query: "enterprise release", limit: 3 },
};

function mcpServerDiscoveryPayload() {
  return {
    ...mcpServer,
    registered_runtime_configs: [capabilityRuntimeConfig],
  };
}
const toolExecuteResult = {
  tool_call: {
    ...runWorkspace.tool_calls[0],
    id: "toolcall-test-invoke-enterprise",
    output_summary: "Capability test invocation completed",
  },
  allowed: true,
  output: {
    status: "ok",
    result: "Enterprise fixture capability returned controlled output.",
  },
};

const modelSettings = {
  default_provider: "openai-compatible",
  default_model: "gpt-5.5",
  providers: [
    { name: "deepseek-flash", label: "DeepSeek Flash", model: "deepseek-v4-flash", api_format: "openai", base_url: "https://api.deepseek.com", rate_limit_rpm: 300, rate_limit_tpm: 1000000 },
    { name: "openai-compatible", label: "OpenAI GPT-5.5", model: "gpt-5.5", api_format: "openai", base_url: "https://api.openai.com/v1", rate_limit_rpm: 600, rate_limit_tpm: 120000 },
    { name: "kimi", label: "Kimi K2.6", model: "kimi-k2.6", api_format: "openai", base_url: "https://api.moonshot.cn/v1", rate_limit_rpm: 300, rate_limit_tpm: 120000 },
    { name: "z-ai", label: "Z.AI GLM-5.1", model: "glm-5.1", api_format: "openai", base_url: "https://api.z.ai/api/paas/v4", rate_limit_rpm: 300, rate_limit_tpm: 120000 },
  ],
  rate_limits: { rpm: 600, tpm: 120000 },
  health: { status: "healthy", updated_at: now, mode: "mock", latency_ms: 12, error_message: null },
  circuit_breaker: { failure_threshold: 3, cooldown_seconds: 60 },
};
const modelHealth = { items: [{ provider: "deepseek-flash", model: "deepseek-v4-flash", status: "healthy", mode: "probe", checked_at: now, latency_ms: 12, error_message: null, circuit_status: "closed", circuit_open_until: null, consecutive_failures: 0 }] };
const modelFallbacks = { organization_id: enterpriseIds.orgId, fallback_total: 1, primary_failure_total: 1, providers: [{ name: "deepseek-pro", count: 1 }], recent_events: [{ event_id: "fallback-1", task_id: enterpriseIds.runId, sequence: 2, primary_provider: "deepseek-flash", primary_model: "deepseek-v4-flash", fallback_provider: "deepseek-pro", fallback_model: "deepseek-v4-pro", fallback_index: 1, reason: "timeout", trace_id: enterpriseIds.traceId, created_at: now }] };
export const modelPricingSources = {
  schema_version: "model_pricing_sources.v1",
  retrieved_at: now,
  parser_version: "manual-official-source-2026-05-30",
  blocking_statuses: ["missing_pricing", "price_unverified", "sku_ambiguous", "currency_conversion_required", "stale", "invalid_pricing"],
  items: [
    pricingSource("DeepSeek Flash", "deepseek-flash", "deepseek-v4-flash", "USD", "0.14", "0.0028", "0.28", "0.00014", "0.0000028", "0.00028", "verified", false, "https://api-docs.deepseek.com/quick_start/pricing"),
    pricingSource("OpenAI GPT-5.5", "openai-compatible", "gpt-5.5", "USD", "5", "0.5", "30", "0.005", "0.0005", "0.030", "verified", false, "https://developers.openai.com/api/docs/pricing"),
    pricingSource("Kimi K2.6", "kimi", "kimi-k2.6", "USD", "0.95", "0.16", "4.00", "0.00095", "0.00016", "0.00400", "verified", false, "https://platform.kimi.ai/docs/pricing/chat-k26"),
    pricingSource("Z.AI GLM-5.1", "z-ai", "glm-5.1", "USD", "1.4", "0.26", "4.4", "0.0014", "0.00026", "0.0044", "verified", false, "https://docs.z.ai/guides/overview/pricing"),
  ],
};

function pricingSource(displayName: string, provider: string, model: string, currency: string, input: string | null, cached: string | null, output: string | null, promptUsd: string | null, cacheUsd: string | null, completionUsd: string | null, status: string, blocks: boolean, officialUrl: string) {
  return { provider, model, mapped_provider: provider, mapped_model: model, display_name: displayName, official_url: officialUrl, retrieved_at: now, unit: "per_1m_tokens", currency, input_per_1m: input, cached_input_per_1m: cached, output_per_1m: output, prompt_per_1k_usd: promptUsd, cache_prompt_per_1k_usd: cacheUsd, completion_per_1k_usd: completionUsd, verification_status: status, valid_from: now, valid_until: null, region: blocks ? "official-currency-dependent" : "global", token_tier: blocks ? "tiered" : "all", mode: provider === "kimi" ? "chat-k26" : "openai-compatible", context_window_tokens: contextWindowForPricingSource(provider, model), max_output_tokens: provider.startsWith("deepseek") ? 384000 : null, source_hash: "a".repeat(64), source_excerpt: "Official pricing excerpt", notes: "Official source fixture", blocks_usd_rollup: blocks };
}

function contextWindowForPricingSource(provider: string, model: string) {
  if (provider === "openai-compatible" && model.startsWith("gpt-5.")) return 272000;
  if (provider === "kimi") return 262144;
  if (provider === "z-ai") return 200000;
  return 1000000;
}

const policySettings = { risk_levels: [{ name: "low", requires_sandbox: false, approval: "auto" }, { name: "high", requires_sandbox: true, approval: "admin" }], approvals: { manual_review: true, deny_on_missing_policy: true }, sandbox: { default_network: false, default_timeout_seconds: 60, memory_mb: 1024, cpus: "1.0", workspace_quota_mb: 1024, network_allowlist: [] }, audit: { model_calls: true, tool_calls: true, policy_actions: true }, web_research: { enabled: false, require_allowlist: true, allow_domains: [], deny_domains: [], max_results: 2, timeout_seconds: 8, max_content_bytes: 1200, max_calls_per_run: 1 }, context_assembly_v2_enabled: true };
const userMember = { membership_id: "member-enterprise", user_id: "dev-engineer", email: "engineer@dev.local", name: "Dev Engineer", role: "admin", invited_at: now, accepted_at: now, status: "active" };
const apiKey = { id: "apikey-enterprise", organization_id: enterpriseIds.orgId, user_id: "dev-engineer", name: "CI Key", key_prefix: "hk_live_", scope_json: ["run:read"], expires_at: null, last_used_at: now, created_at: now, revoked_at: null };
const auditEvent = { id: "audit-enterprise", organization_id: enterpriseIds.orgId, actor_id: "dev-engineer", event_type: "ADMIN_ACTION", resource_type: "team", resource_id: enterpriseIds.teamId, action: "team.subagent.projected", payload_json: { subagent_id: enterpriseIds.subagentId }, created_at: now };
const retentionPolicy = { id: "retention-enterprise", organization_id: null, entity_type: "model_calls", action: "archive", retention_days: 90, delete_after_days: 365, enabled: true, created_at: now, updated_at: now };
const retentionRun = { id: "retention-run-enterprise", policy_id: "retention-enterprise", organization_id: enterpriseIds.orgId, entity_type: "model_calls", action: "archive", deleted_count: 0, archived_count: 1, started_at: now, finished_at: now, error_message: null };
const dataExport = { id: "export-enterprise", organization_id: enterpriseIds.orgId, requested_by: "dev-engineer", status: "completed", requested_at: now, completed_at: now, file_path: "/tmp/export.json", file_sha256: "b".repeat(64), size_bytes: 2048, expires_at: null, error_message: null };
const frontendError = { id: "frontend-error-enterprise", organization_id: enterpriseIds.orgId, user_id: "dev-engineer", url: "http://127.0.0.1/settings/frontend-errors", user_agent: "Playwright", error_message: "Route smoke captured handled error", stack: "Error: handled", component_stack: null, metadata_json: { route: "/settings/frontend-errors" }, created_at: now };
const frontendErrorSummary = { error_message: frontendError.error_message, count: 1, affected_users: 1, last_seen_at: now };

const warmPool = { enabled: true, idle: 2, busy: 1, failed: 0, min_size: 2, max_size: 5, hit_total: 9, miss_total: 1 };
const sandboxQuotaUsage = {
  organization_id: enterpriseIds.orgId,
  configured_memory_mb: 2048,
  configured_cpus: "1.0",
  configured_workspace_quota_mb: 4096,
  configured_network_enabled: true,
  configured_network_allowlist: ["api.deepseek.com"],
  sandbox_total: 3,
  running_total: 1,
  destroyed_total: 2,
  memory_limit_mb_total: 3072,
  running_memory_limit_mb_total: 1024,
  cpu_limit_total: 3,
  running_cpu_limit_total: 1,
  network_enabled_total: 1,
  warm_pool_reused_total: 1,
  latest_created_at: now,
};
const sandboxQuotaHistory = {
  id: enterpriseIds.sandboxId,
  task_id: enterpriseIds.runId,
  container_id: "container-enterprise",
  status: "running",
  cpu_limit: "1.0",
  cpu_limit_value: 1,
  memory_limit_mb: 1024,
  network_enabled: true,
  warm_pool_reused: true,
  lifetime_seconds: 120,
  created_at: now,
  destroyed_at: null,
};
const warmPoolBenchmark = { id: "benchmark-enterprise", organization_id: enterpriseIds.orgId, mode: "projection", status: "completed", target_startup_ms: 50, iteration_count: 5, warm_avg_ms: 12, warm_p95_ms: 18, cold_avg_ms: 80, hit_rate: 90, report_json: {}, created_by: "dev-engineer", created_at: now };

const observabilitySummary = {
  task_total: 1,
  failed_task_total: 0,
  event_total: 3,
  model_call_total: 1,
  tool_call_total: 1,
  sandbox_total: 1,
  active_runs: 0,
  token_optimization: { estimated_saved_tokens: 3000, actual_total_tokens: 7000, low_cost_route_count: 1 },
  tasks_by_status: [{ name: "COMPLETED", count: 1 }],
  subagents_by_status: [{ name: "SUCCESS", count: 1 }],
  agent_assignments_by_status: [],
  model_calls_by_status: [{ name: "COMPLETED", count: 1 }],
  tool_calls_by_status: [{ name: "COMPLETED", count: 1 }],
  subagent_queue: { pending: 0, queued: 0, running: 0, success: 1, failed: 0, timeout: 0, cancelled: 0 },
  assignment_queue: { pending: 0, running: 0 },
  warm_pool: warmPool,
  sandboxes_by_status: [{ name: "running", count: 1 }],
};
const tokenSavings = {
  generated_at: now,
  summary: {
    actual_prompt_tokens: 1000,
    actual_completion_tokens: 500,
    actual_total_tokens: 1500,
    estimated_candidate_tokens: 2200,
    estimated_included_tokens: 1500,
    estimated_omitted_tokens: 700,
    estimated_saved_tokens: 700,
    estimated_savings_percent: 31.82,
    context_manifest_count: 1,
    pruning_manifest_count: 1,
    retrieval_cache_hit_count: 2,
    retrieval_cache_miss_count: 1,
    retrieval_cache_stale_count: 0,
    cache_sources: [
      {
        cache_source: "compression_summary",
        label: "摘要缓存",
        hit_count: 2,
        miss_count: 1,
        stale_count: 0,
        estimated_saved_tokens: 180,
        hit_rate: 66.67,
        reason: "summary_reused",
      },
    ],
    low_cost_route_count: 1,
    optimizer_capability_version_ids: ["balanced-version-enterprise"],
    optimizer_labels: ["Balanced"],
    optimizer_decision_count: 1,
  },
  runs: [
    {
      run_id: enterpriseIds.runId,
      agent_id: enterpriseIds.agentId,
      model_names: ["deepseek-v4-flash"],
      title: "Balanced optimizer run",
      status: "COMPLETED",
      created_at: now,
      updated_at: now,
      context_manifest_id: "manifest-enterprise-token-savings",
      estimated_candidate_tokens: 2200,
      estimated_included_tokens: 1500,
      estimated_omitted_tokens: 700,
      estimated_saved_tokens: 700,
      estimated_savings_percent: 31.82,
      actual_prompt_tokens: 1000,
      actual_completion_tokens: 500,
      actual_total_tokens: 1500,
      included_count: 3,
      omitted_count: 2,
      pruning_applied: true,
      retrieval_cache_hit_count: 2,
      retrieval_cache_miss_count: 1,
      retrieval_cache_stale_count: 0,
      cache_sources: [
        {
          cache_source: "compression_summary",
          label: "摘要缓存",
          hit_count: 2,
          miss_count: 1,
          stale_count: 0,
          estimated_saved_tokens: 180,
          hit_rate: 66.67,
          reason: "summary_reused",
        },
      ],
      low_cost_routes: [
        {
          model_call_id: "model-call-enterprise",
          model_name: "deepseek-v4-flash",
          reason: "balanced route stayed within budget",
        },
      ],
      optimizer_capability_version_ids: ["balanced-version-enterprise"],
      optimizer_labels: ["Balanced"],
      optimizer_policy_hash: "policy-enterprise",
      optimizer_decision_count: 1,
      omission_reasons: [{ reason: "optimizer_budget", count: 2 }],
    },
  ],
  next_cursor: null,
};
export const costRollup = { window: "7d", group_by: "provider", generated_at: now, total_cost_usd: 0.00028, total_tokens: 1500, total_runs: 1, average_run_cost_usd: 0.00028, breakdown: [{ key: "deepseek-flash/deepseek-v4-flash", label: "deepseek-flash/deepseek-v4-flash", cost_usd: 0.00028, tokens_in: 1000, tokens_out: 500, run_count: 1, share: 1, pricing_status: "verified", pricing_blocking: false }, { key: "unknown-provider/unknown-model", label: "unknown-provider/unknown-model", cost_usd: 0, tokens_in: 10, tokens_out: 5, run_count: 1, share: 0, pricing_status: "missing_pricing", pricing_blocking: true }], series: [], pricing_statuses: [{ model: "deepseek-flash/deepseek-v4-flash", status: "verified", blocking: false }, { model: "unknown-provider/unknown-model", status: "missing_pricing", blocking: true }] };
const groundingQuality = {
  items: [
    {
      eval_run_id: enterpriseIds.evalRunId,
      eval_result_id: "eval-result-enterprise",
      eval_case_id: "case-enterprise",
      task_id: enterpriseIds.runId,
      dataset_id: "dataset-enterprise",
      agent_id: enterpriseIds.agentId,
      status: "PASSED",
      created_at: now,
      grounding_passed: true,
      grounding_failures: [],
      forbidden_evidence_leaked: false,
      forbidden_leak_sources: [],
      fallback_expected: false,
      fallback_observed: false,
      unsupported_marker_present: false,
      citation_keys: ["release-grounding"],
      citation_hit_ids: ["knowledge-document-enterprise"],
      retrieval_session_id: "retrieval-enterprise",
      prompt_manifest_id: null,
    },
  ],
  metrics: {
    grounding_pass_rate: 1,
    citation_coverage_rate: 1,
    forbidden_evidence_leak_rate: 0,
    fallback_mismatch_rate: 0,
    unsupported_marker_rate: 0,
    grounding_failure_total: 0,
    required_evidence_miss_rate: 0,
  },
  failure_facets: [],
  total: 1,
};
const logLine = {
  timestamp: now,
  level: "info",
  message: "enterprise trace linked",
  trace_id: enterpriseIds.traceId,
  task_id: enterpriseIds.runId,
  agent_run_id: enterpriseIds.subagentId,
  event_type: "team.subagent.project",
  payload_json: { subagent_id: enterpriseIds.subagentId, local_evidence: true },
  service: "api",
  source: "fixture",
};
const traceListItem = {
  trace_id: enterpriseIds.traceId,
  task_id: enterpriseIds.runId,
  root_name: "team.subagent.project",
  start_time: now,
  duration_ms: 120,
  span_count: 1,
  status: "ok",
  source: "otel",
};
const traceDetail = {
  trace_id: enterpriseIds.traceId,
  source: "otel",
  service_nodes: [{ service: "api", span_count: 1, error_count: 0, total_duration_ms: 120 }],
  service_edges: [],
  spans: [
    {
      trace_id: enterpriseIds.traceId,
      span_id: "span-1",
      parent_span_id: null,
      name: "team.subagent.project",
      service: "api",
      start_time: now,
      end_time: now,
      duration_ms: 120,
      kind: "internal",
      status: "ok",
      task_id: enterpriseIds.runId,
      agent_run_id: enterpriseIds.subagentId,
      attributes: { subagent_id: enterpriseIds.subagentId },
      source: "otel",
    },
  ],
};
const alertRule = {
  id: enterpriseIds.alertRuleId,
  organization_id: enterpriseIds.orgId,
  name: "Cost Gate",
  metric: "pricing_blocking_count",
  comparator: ">",
  threshold: 0,
  window_seconds: 300,
  severity: "warning",
  enabled: true,
  notification_channels_json: ["in_app", "webhook:Release Webhook"],
  created_at: now,
  updated_at: now,
};
const alertEvent = {
  id: "alert-event-enterprise",
  rule_id: enterpriseIds.alertRuleId,
  rule_name: "Cost Gate",
  organization_id: enterpriseIds.orgId,
  metric: "pricing_blocking_count",
  comparator: ">",
  threshold: 0,
  observed_value: 1,
  severity: "warning",
  status: "active",
  message: "Unknown model pricing is missing",
  context_json: { run_id: enterpriseIds.runId },
  triggered_at: now,
  resolved_at: null,
};
const notificationChannel = { id: "channel-enterprise", organization_id: enterpriseIds.orgId, name: "Release Webhook", kind: "webhook", config_json: { url: "https://example.com" }, verified: true, created_by: "dev-engineer", created_at: now, updated_at: now };

const evalDataset = { id: "dataset-enterprise", organization_id: enterpriseIds.orgId, name: "Enterprise Cost Gate", description: "Regression chain", status: "active", baseline_run_id: null, created_by: "dev-engineer", created_at: now, updated_at: now, case_count: 1 };
const evalCase = { id: "case-enterprise", dataset_id: evalDataset.id, source_task_id: enterpriseIds.runId, input_json: {}, expected_json: { status: "COMPLETED", cost_contract: { enterprise_gate: true } }, tags_json: ["enterprise"], created_at: now };
const evalResult = {
  id: "eval-result-enterprise",
  eval_run_id: enterpriseIds.evalRunId,
  eval_case_id: evalCase.id,
  task_id: enterpriseIds.runId,
  status: "FAILED",
  scores_json: { task_success: 0, cost_contract_score: 0 },
  grader_trace_json: {
    grader: "enterprise-pricing-gate",
    passed: false,
    grounding_failures: [],
    forbidden_leak_sources: [],
    cost_contract: {
      configured: true,
      passed: false,
      failures: ["pricing_blocking_statuses", "missing_pricing"],
      actual_cost_usd: "0",
      prompt_tokens: 1000,
      completion_tokens: 500,
    },
  },
  latency_ms: 400,
  cost_usd: "0.000000",
  error_message: null,
  created_at: now,
};
const evalRun = {
  id: enterpriseIds.evalRunId,
  dataset_id: evalDataset.id,
  organization_id: enterpriseIds.orgId,
  agent_id: enterpriseIds.agentId,
  status: "COMPLETED",
  metrics_json: {
    task_success_rate: 0,
    cost_contract_pass_rate: 0,
    cost_contract_configured_count: 1,
    cost_contract_failure_breakdown: { pricing_blocking_statuses: 1, missing_pricing: 1 },
    pricing_blocking_statuses: ["missing_pricing"],
  },
  created_by: "dev-engineer",
  started_at: now,
  completed_at: now,
  created_at: now,
  results: [evalResult],
};
const regressionDelta = {
  baseline_run_id: "baseline-enterprise",
  current_run_id: enterpriseIds.evalRunId,
  task_success_rate_delta: 0,
  tool_selection_accuracy_delta: 0,
  avg_latency_ms_delta: 0,
  grounding_pass_rate_delta: 0,
  citation_coverage_rate_delta: 0,
  unsupported_marker_rate_delta: 0,
  fallback_mismatch_rate_delta: 0,
  forbidden_evidence_leak_rate_delta: 0,
  required_evidence_miss_rate_delta: 0,
  tool_contract_pass_rate_delta: 0,
  dialogue_contract_pass_rate_delta: 0,
  cost_contract_pass_rate_delta: 0,
  refusal_contract_pass_rate_delta: 0,
  safety_contract_pass_rate_delta: 0,
  persona_contract_pass_rate_delta: 0,
  specialist_contract_pass_rate_delta: 0,
  overrefusal_rate_delta: 0,
  safety_violation_total_delta: 0,
  role_drift_total_delta: 0,
  avg_cost_usd_delta: "0",
  total_cost_usd_delta: "0",
  total_prompt_tokens_delta: 0,
  total_completion_tokens_delta: 0,
  newly_failing_case_ids: [],
  newly_passing_case_ids: [],
  newly_grounding_failing_case_ids: [],
  newly_forbidden_leak_case_ids: [],
  is_regression: false,
  total_cases: 1,
  passed_cases: 0,
  failed_cases: 1,
  grounding_sample_count: 1,
  low_sample_count: false,
  low_sample_caveat: null,
};
const recoverySummary = { batch_total: 0, task_total: 0, scanned_total: 0, recovered_total: 0, lock_skipped_total: 0, action_counts: {}, tasks: [], recent_batches: [], latest_completed_at: null };
const recoveryGlobalSummary = { organization_count: 1, batch_total: 0, recovered_total: 0, organizations: [] };
const taskResult = {
  task_id: enterpriseIds.runId,
  status: "COMPLETED",
  summary: "Enterprise chain complete.",
  execution_plan: runWorkspace.plan,
  artifacts: [{ name: "enterprise-report.md", artifact_type: "text", description: "Enterprise evidence", status: "created" }],
  subagent_results: [
    {
      id: enterpriseIds.subagentId,
      step_key: "review-release-chain",
      status: "SUCCESS",
      fanout_batch_id: "fanout-enterprise",
      fanout_index: 0,
      fanout_total: 2,
      specialist_slug: "code-reviewer",
      specialist_role: "reviewer",
      specialist_output: { result: "passed", summary: "Team bridge output" },
      budget_consumed_json: { cost_usd: "0.000280", prompt_tokens: 1000, completion_tokens: 500 },
      budget_exceeded_json: [],
      summary: "Team bridge output",
      tool_results: [{ tool_call_id: "toolcall-enterprise", tool_name: "read_file", status: "COMPLETED", allowed: true, duration_ms: 20, input_json: { path: "README.md" }, output: { content: "Harness" }, error_message: null }],
      artifacts: [],
      react_trace: [],
      context_summary: { total_tool_results: 1, retained_tool_results: 1, omitted_tool_results: 0 },
      completed_at: now,
    },
  ],
  last_sequence: 3,
  pending: false,
};
const fanoutBatches = {
  items: [
    {
      fanout_batch_id: "fanout-enterprise",
      task_id: enterpriseIds.runId,
      step_key: "review-release-chain",
      fanout_total: 2,
      aggregation: "synthesizer_chain",
      statuses: { SUCCESS: 1, RUNNING: 1 },
      members: [
        { id: enterpriseIds.subagentId, status: "SUCCESS", specialist_id: enterpriseIds.specialistId, specialist_slug: "code-reviewer", fanout_index: 0, dynamic_fanout_origin: null, dynamic_fanout_requested_by: null, dynamic_fanout_reason: null, output_id: "subagent-output-enterprise" },
        { id: "subagent-enterprise-security", status: "RUNNING", specialist_id: null, specialist_slug: "safety-checker", fanout_index: 1, dynamic_fanout_origin: "fanout-enterprise", dynamic_fanout_requested_by: enterpriseIds.subagentId, dynamic_fanout_reason: "enterprise_risk_review", output_id: null },
      ],
      extend_history: [],
    },
  ],
  next_cursor: null,
};
