import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useConsoleStore } from "../../stores/consoleStore";
import { ConsoleShell } from "../ConsoleShell";

describe("ConsoleShell", () => {
  it("embeds the workspace route inside the normal console frame", () => {
    useConsoleStore.getState().setLocale("en-US");

    render(
      <MemoryRouter initialEntries={["/agents/default/workspace"]}>
        <ConsoleShell title="Agent Workspace">
          <div>Workspace child</div>
        </ConsoleShell>
      </MemoryRouter>,
    );

    expect(screen.getByText("Workspace child")).toBeInTheDocument();
    expect(screen.getByText("Console")).toBeInTheDocument();
    expect(screen.getByText("Agent Workspace")).toBeInTheDocument();
    expect(screen.getByLabelText("Expand sidebar")).toBeInTheDocument();
    expect(screen.getByLabelText("Search")).toBeInTheDocument();
  });
});
