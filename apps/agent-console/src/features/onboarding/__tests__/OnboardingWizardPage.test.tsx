import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OnboardingWizardPage } from "../pages/OnboardingWizardPage";
import type { OnboardingState } from "../../tasks/api";

vi.mock("../../../app/ConsoleShell", () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const apiBaseUrl = "http://127.0.0.1:8000";

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestPath(input: RequestInfo | URL) {
  const url = String(input);
  return new URL(url.startsWith("http") ? url : `${apiBaseUrl}${url}`).pathname;
}

function onboardingState(overrides: Partial<OnboardingState> = {}): OnboardingState {
  return {
    id: "onboarding-dev",
    organization_id: "dev-org",
    user_id: "dev-engineer",
    current_step: 4,
    completed: false,
    skipped: false,
    demo_loaded: false,
    provider_json: {},
    agent_id: null,
    demo_task_id: null,
    created_at: "2026-06-15T00:00:00Z",
    updated_at: "2026-06-15T00:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

function renderOnboarding(fetchMock: ReturnType<typeof vi.fn>, initialEntry = "/onboarding?step=4") {
  vi.stubGlobal("fetch", fetchMock);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/" element={<div>看板已打开</div>} />
          <Route path="/onboarding" element={<OnboardingWizardPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("OnboardingWizardPage completion", () => {
  it("closes onboarding after completing setup", async () => {
    const user = userEvent.setup();
    const completed = onboardingState({
      completed: true,
      demo_loaded: true,
      agent_id: "first-run-agent",
      demo_task_id: "demo-run-1",
      completed_at: "2026-06-15T00:01:00Z",
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/onboarding/state" && method === "GET") {
        return jsonResponse(onboardingState());
      }
      if (path === "/api/onboarding/complete" && method === "POST") {
        return jsonResponse(completed);
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderOnboarding(fetchMock);

    await user.click(await screen.findByRole("button", { name: "完成设置" }));

    expect(await screen.findByText("看板已打开")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "完成设置" })).not.toBeInTheDocument();
    });
  });

  it("redirects away when onboarding is already completed", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      const method = init?.method ?? "GET";
      if (path === "/api/onboarding/state" && method === "GET") {
        return jsonResponse(onboardingState({ completed: true, completed_at: "2026-06-15T00:01:00Z" }));
      }
      return jsonResponse({ detail: `unexpected ${method} ${path}` }, 404);
    });

    renderOnboarding(fetchMock, "/onboarding");

    expect(await screen.findByText("看板已打开")).toBeInTheDocument();
    expect(screen.queryByText("首次运行设置")).not.toBeInTheDocument();
  });
});
