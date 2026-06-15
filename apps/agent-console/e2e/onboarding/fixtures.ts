/**
 * Shared fixtures for onboarding wizard E2E tests
 */
import { type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

export type OnboardingState = {
  id: string;
  organization_id: string;
  user_id: string;
  current_step: number;
  completed: boolean;
  skipped: boolean;
  demo_loaded: boolean;
  provider_json: Record<string, unknown>;
  agent_id: string | null;
  demo_task_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type OnboardingFixtureOptions = {
  initialStep?: number;
  shouldFailValidation?: {
    apiKey?: boolean;
    agentCreation?: boolean;
    demoLoad?: boolean;
  };
  autoFixAvailable?: {
    database?: boolean;
    secrets?: boolean;
  };
};

export function createOnboardingState(step = 1): OnboardingState {
  return {
    id: "onboarding-001",
    organization_id: "org-001",
    user_id: "user-001",
    current_step: step,
    completed: false,
    skipped: false,
    demo_loaded: false,
    provider_json: {},
    agent_id: null,
    demo_task_id: null,
    created_at: "2026-06-14T00:00:00.000Z",
    updated_at: "2026-06-14T00:00:00.000Z",
    completed_at: null,
  };
}

function fulfillJson(route: Route, payload: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

export async function setupOnboardingMocks(page: Page, options: OnboardingFixtureOptions = {}) {
  const state = {
    onboarding: createOnboardingState(options.initialStep ?? 1),
    agentCreated: false,
    demoLoaded: false,
    ...options,
  };

  await page.route(API_RE, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    // Auth
    if (path === "/api/auth/me" && method === "GET") {
      await fulfillJson(route, {
        user_id: "user-001",
        email: "test@example.com",
        name: "Test User",
        organization_id: "org-001",
        role: "admin",
        permissions: ["*"],
        organizations: [{ id: "org-001", name: "Test Org", slug: "test-org", role: "admin" }],
      });
      return;
    }

    // Onboarding state - GET
    if (path === "/api/onboarding/state" && method === "GET") {
      await fulfillJson(route, state.onboarding);
      return;
    }

    // Onboarding state - PATCH (update)
    if (path === "/api/onboarding/state" && method === "PATCH") {
      const payload = JSON.parse(request.postData() ?? "{}");

      // Simulate API key validation failure
      if (state.shouldFailValidation?.apiKey && payload.provider_json?.key_configured) {
        await fulfillJson(
          route,
          {
            error: "Invalid API key",
            detail: "The provided API key is invalid or expired",
          },
          400,
        );
        return;
      }

      state.onboarding = {
        ...state.onboarding,
        ...payload,
        updated_at: new Date().toISOString(),
      };
      await fulfillJson(route, state.onboarding);
      return;
    }

    // Create agent
    if (path === "/api/agents/definitions" && method === "POST") {
      const payload = JSON.parse(request.postData() ?? "{}");

      // Simulate agent creation failure
      if (state.shouldFailValidation?.agentCreation) {
        await fulfillJson(
          route,
          {
            error: "Agent creation failed",
            detail: "Agent ID already exists or validation failed",
          },
          400,
        );
        return;
      }

      // Validate required fields
      if (!payload.id?.trim()) {
        await fulfillJson(
          route,
          {
            error: "Validation error",
            detail: "Agent ID cannot be empty",
          },
          400,
        );
        return;
      }

      if (!payload.name?.trim()) {
        await fulfillJson(
          route,
          {
            error: "Validation error",
            detail: "Agent name cannot be empty",
          },
          400,
        );
        return;
      }

      state.agentCreated = true;
      state.onboarding.agent_id = payload.id;

      await fulfillJson(
        route,
        {
          id: payload.id,
          name: payload.name,
          description: payload.description,
          role: payload.role,
          model_provider: payload.model_provider,
          model_name: payload.model_name,
          status: "ACTIVE",
          system_prompt: payload.system_prompt,
          tools_json: payload.tools_json ?? [],
          routing_tags: payload.routing_tags ?? [],
          max_parallel_assignments: payload.max_parallel_assignments ?? 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        201,
      );
      return;
    }

    // Load demo data
    if (path === "/api/demo/load" && method === "POST") {
      // Simulate demo load failure
      if (state.shouldFailValidation?.demoLoad) {
        await fulfillJson(
          route,
          {
            error: "Demo load failed",
            detail: "Failed to initialize demo data. Please check system configuration.",
          },
          500,
        );
        return;
      }

      state.demoLoaded = true;
      state.onboarding.demo_task_id = "demo-task-001";

      await fulfillJson(route, {
        status: "loaded",
        agent_ids: [state.onboarding.agent_id ?? "first-run-agent"],
        task_id: "demo-task-001",
      });
      return;
    }

    // Complete onboarding
    if (path === "/api/onboarding/complete" && method === "POST") {
      state.onboarding.completed = true;
      state.onboarding.completed_at = new Date().toISOString();
      await fulfillJson(route, state.onboarding);
      return;
    }

    // Get agents list (may be called by other parts of the app)
    if (path === "/api/agents/definitions" && method === "GET") {
      await fulfillJson(route, {
        items: state.onboarding.agent_id
          ? [
              {
                id: state.onboarding.agent_id,
                name: "First Agent",
                status: "ACTIVE",
              },
            ]
          : [],
        next_cursor: null,
      });
      return;
    }

    // System health check (hypothetical for auto-fix tests)
    if (path === "/api/system/health" && method === "GET") {
      await fulfillJson(route, {
        database: { status: "healthy" },
        secrets: { status: "configured" },
        models: { status: "available" },
      });
      return;
    }

    // Auto-fix endpoints (hypothetical)
    if (path === "/api/system/auto-fix/database" && method === "POST") {
      if (!state.autoFixAvailable?.database) {
        await fulfillJson(
          route,
          {
            error: "Auto-fix not available",
            detail: "Database is already initialized or manual intervention required",
          },
          400,
        );
        return;
      }

      await fulfillJson(route, {
        success: true,
        message: "Database tables created and migrations applied",
      });
      return;
    }

    if (path === "/api/system/auto-fix/secrets" && method === "POST") {
      if (!state.autoFixAvailable?.secrets) {
        await fulfillJson(
          route,
          {
            error: "Auto-fix not available",
            detail: "Secrets are already configured or manual setup required",
          },
          400,
        );
        return;
      }

      await fulfillJson(route, {
        success: true,
        message: "JWT secret and encryption keys generated",
        secrets_generated: ["JWT_SECRET", "ENCRYPTION_KEY"],
      });
      return;
    }

    // Fallback for unhandled routes - return empty success responses
    // This prevents the app from showing error pages for optional API calls
    if (method === "GET") {
      await fulfillJson(route, { items: [], next_cursor: null });
      return;
    }

    await fulfillJson(
      route,
      {
        error: "Not found",
        detail: `Unhandled route: ${method} ${path}`,
      },
      404,
    );
  });

  return state;
}
