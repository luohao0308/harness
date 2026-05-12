import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useConsoleStore } from "../../../stores/consoleStore";
import { WorkspaceShellBar } from "../components/WorkspaceShellBar";

function renderShell(overrides: Partial<Parameters<typeof WorkspaceShellBar>[0]> = {}) {
  const props: Parameters<typeof WorkspaceShellBar>[0] = {
    agentId: "default",
    agentName: "Default Agent",
    activeRunId: null,
    runStatus: undefined,
    isStreaming: false,
    onOpenInspector: vi.fn(),
    onStop: vi.fn(),
    ...overrides,
  };

  render(
    <MemoryRouter>
      <WorkspaceShellBar {...props} />
    </MemoryRouter>,
  );

  return props;
}

describe("WorkspaceShellBar", () => {
  it("keeps the Workspace title controls visible without the old metric row", () => {
    useConsoleStore.getState().setLocale("en-US");
    renderShell();

    expect(screen.getByRole("link", { name: "Back to Agent Studio" })).toHaveAttribute(
      "href",
      "/agents",
    );
    expect(screen.getByText("Default Agent")).toBeInTheDocument();
    expect(screen.getByText(/Model \+ Harness = Agent/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Model:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Context:/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Tools:/ })).not.toBeInTheDocument();
    expect(screen.getByLabelText("No run yet")).toBeInTheDocument();
  });

  it("links to Run Detail after a run exists", () => {
    useConsoleStore.getState().setLocale("en-US");

    renderShell({
      activeRunId: "run-123",
      runStatus: "WAITING_APPROVAL",
    });

    expect(screen.getByRole("link", { name: "Run Detail" })).toHaveAttribute(
      "href",
      "/runs/run-123",
    );
    expect(screen.getByText("WAITING_APPROVAL")).toBeInTheDocument();
  });
});
