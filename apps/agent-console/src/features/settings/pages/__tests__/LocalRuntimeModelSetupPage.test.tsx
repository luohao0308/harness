import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocalRuntimeModelSetupPage } from "../LocalRuntimeModelSetupPage";

const apiMock = vi.hoisted(() => ({
  getLocalRuntimeModelStatus: vi.fn(),
}));

vi.mock("../../../tasks/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../tasks/api")>()),
  getLocalRuntimeModelStatus: apiMock.getLocalRuntimeModelStatus,
}));

const setupRequired = {
  state: "setup_required" as const,
  provider: "shipped-provider",
  model: "shipped-model",
  base_url: "https://models.example/v1",
  secret_storage: "persistent" as const,
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LocalRuntimeModelSetupPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LocalRuntimeModelSetupPage", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_RUNTIME_PROFILE", "local");
    apiMock.getLocalRuntimeModelStatus.mockReset();
    apiMock.getLocalRuntimeModelStatus.mockResolvedValue(setupRequired);
    delete window.desktopApi;
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete window.desktopApi;
  });

  it("keeps the browser Web Extension read-only", async () => {
    renderPage();

    expect(await screen.findByText(/Open Forge Harness Desktop/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Model API key")).not.toBeInTheDocument();
  });

  it("saves a Desktop key only through preload IPC and never sends it to fetch", async () => {
    const setModelApiKey = vi.fn(async () => ({ ...setupRequired, state: "healthy" as const }));
    apiMock.getLocalRuntimeModelStatus
      .mockResolvedValueOnce(setupRequired)
      .mockResolvedValue({ ...setupRequired, state: "healthy" as const });
    window.desktopApi = { localRuntime: { setModelApiKey } };
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderPage();

    fireEvent.change(await screen.findByLabelText("Model API key"), {
      target: { value: "sk-desktop-canary" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));

    await waitFor(() => {
      expect(setModelApiKey).toHaveBeenCalledWith("sk-desktop-canary");
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
