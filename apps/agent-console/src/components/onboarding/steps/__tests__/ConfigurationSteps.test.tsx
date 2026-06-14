import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FirstAgentStep } from "../FirstAgentStep";
import { KnowledgeBaseStep } from "../KnowledgeBaseStep";
import { ModelProviderStep } from "../ModelProviderStep";
import { ToolConfigStep } from "../ToolConfigStep";

describe("ModelProviderStep", () => {
  it("renders form fields for model provider configuration", () => {
    const onSubmit = vi.fn();
    render(<ModelProviderStep onSubmit={onSubmit} />);

    expect(screen.getByLabelText(/api key/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/base url/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/model/i)).toBeInTheDocument();
  });

  it("validates required fields and shows error messages", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ModelProviderStep onSubmit={onSubmit} />);

    const submitButton = screen.getByRole("button", { name: /save/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/api key is required/i)).toBeInTheDocument();
    });

    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("FirstAgentStep", () => {
  it("renders form fields for agent creation", () => {
    const onSubmit = vi.fn();
    render(<FirstAgentStep onSubmit={onSubmit} />);

    expect(screen.getByLabelText(/agent name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/system prompt/i)).toBeInTheDocument();
  });

  it("validates agent name length and shows error", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<FirstAgentStep onSubmit={onSubmit} />);

    const nameInput = screen.getByLabelText(/agent name/i);
    await user.type(nameInput, "ab");

    const submitButton = screen.getByRole("button", { name: /save/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/name must be at least 3 characters/i)).toBeInTheDocument();
    });

    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("KnowledgeBaseStep", () => {
  it("renders file upload and URL input options", () => {
    const onSubmit = vi.fn();
    render(<KnowledgeBaseStep onSubmit={onSubmit} />);

    expect(screen.getByText(/upload files/i)).toBeInTheDocument();
    expect(screen.getByText(/add url/i)).toBeInTheDocument();
  });

  it("validates URL format and shows error", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<KnowledgeBaseStep onSubmit={onSubmit} />);

    const urlInput = screen.getByLabelText(/add url/i);
    await user.type(urlInput, "not-a-valid-url");

    const submitButton = screen.getByRole("button", { name: /save/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/invalid url/i)).toBeInTheDocument();
    });

    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("ToolConfigStep", () => {
  it("renders available tools as checkboxes", () => {
    const onSubmit = vi.fn();
    render(<ToolConfigStep onSubmit={onSubmit} />);

    expect(screen.getByLabelText(/web search/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/code execution/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/file operations/i)).toBeInTheDocument();
  });

  it("requires at least one tool to be selected", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ToolConfigStep onSubmit={onSubmit} />);

    const submitButton = screen.getByRole("button", { name: /save/i });
    await user.click(submitButton);

    await waitFor(() => {
      const errorMessages = screen.getAllByText(/select at least one tool/i);
      expect(errorMessages.length).toBeGreaterThan(0);
    });

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
