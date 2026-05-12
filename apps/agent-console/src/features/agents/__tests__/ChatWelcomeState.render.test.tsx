import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { useConsoleStore } from "../../../stores/consoleStore";
import { ChatWelcomeState } from "../components/ChatWelcomeState";
import { EXAMPLE_PROMPTS } from "../lib/examplePrompts";

describe("ChatWelcomeState", () => {
  it("renders a chat-first empty state and keeps prompt picks wired", async () => {
    useConsoleStore.getState().setLocale("en-US");
    const user = userEvent.setup();
    const onPickPrompt = vi.fn();

    render(
      <ChatWelcomeState
        agentName="Default Agent"
        modelLabel="openai / test-model"
        onPickPrompt={onPickPrompt}
      />,
    );

    expect(screen.getByText("Where should we start?")).toBeInTheDocument();
    expect(screen.getByText(/Default Agent/)).toBeInTheDocument();

    const firstPrompt = EXAMPLE_PROMPTS[0].en;
    await user.click(screen.getByRole("button", { name: firstPrompt }));

    expect(onPickPrompt).toHaveBeenCalledWith(firstPrompt);
  });
});
