import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ModelProviderStep } from "../ModelProviderStep";
import { FirstAgentStep } from "../FirstAgentStep";
import { KnowledgeBaseStep } from "../KnowledgeBaseStep";
import { ToolConfigStep } from "../ToolConfigStep";

describe("Onboarding Forms - Validation Tests", () => {
  describe("ModelProviderStep - Validation", () => {
    it("shows error for empty API key field", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<ModelProviderStep onSubmit={onSubmit} />);

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("API key is required")).toBeInTheDocument();
      });
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("shows error for invalid base URL format", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<ModelProviderStep onSubmit={onSubmit} />);

      const apiKeyInput = screen.getByLabelText(/^api key\b/i);
      const baseUrlInput = screen.getByLabelText(/base url/i);
      const modelSelect = screen.getByLabelText(/model/i);

      await user.type(apiKeyInput, "sk-test-key");
      await user.type(baseUrlInput, "not-a-valid-url");
      await user.selectOptions(modelSelect, "gpt-4");

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Base URL must be a valid URL")).toBeInTheDocument();
      });
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("shows error when model is not selected", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<ModelProviderStep onSubmit={onSubmit} />);

      const apiKeyInput = screen.getByLabelText(/^api key\b/i);
      const baseUrlInput = screen.getByLabelText(/base url/i);

      await user.type(apiKeyInput, "sk-test-key");
      await user.type(baseUrlInput, "https://api.openai.com/v1");

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Model selection is required")).toBeInTheDocument();
      });
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("validates all required fields at once on submit", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<ModelProviderStep onSubmit={onSubmit} />);

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("API key is required")).toBeInTheDocument();
        expect(screen.getByText("Base URL must be a valid URL")).toBeInTheDocument();
        expect(screen.getByText("Model selection is required")).toBeInTheDocument();
      });
      expect(onSubmit).not.toHaveBeenCalled();
    });
  });

  describe("FirstAgentStep - Validation", () => {
    it("shows error for agent name less than 3 characters", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<FirstAgentStep onSubmit={onSubmit} />);

      const nameInput = screen.getByLabelText(/agent name/i);
      await user.type(nameInput, "ab");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText("Agent name must be at least 3 characters")).toBeInTheDocument();
      });
    });

    it("shows error for agent name exceeding 50 characters", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<FirstAgentStep onSubmit={onSubmit} />);

      const nameInput = screen.getByLabelText(/agent name/i);
      await user.type(nameInput, "a".repeat(51));
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText("Agent name must be less than 50 characters")).toBeInTheDocument();
      });
    });

    it("shows error for description less than 10 characters", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<FirstAgentStep onSubmit={onSubmit} />);

      const descriptionInput = screen.getByLabelText(/description/i);
      await user.type(descriptionInput, "short");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText("Description must be at least 10 characters")).toBeInTheDocument();
      });
    });

    it("shows error for system prompt less than 20 characters", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<FirstAgentStep onSubmit={onSubmit} />);

      const systemPromptInput = screen.getByLabelText(/system prompt/i);
      await user.type(systemPromptInput, "too short");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText("System prompt must be at least 20 characters")).toBeInTheDocument();
      });
    });
  });

  describe("KnowledgeBaseStep - Validation", () => {
    it("shows error for invalid URL format", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<KnowledgeBaseStep onSubmit={onSubmit} />);

      const urlInput = screen.getByLabelText(/add url/i);
      await user.type(urlInput, "not-a-valid-url");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText("Invalid URL format")).toBeInTheDocument();
      });
    });

    it("shows error when neither URL nor files are provided", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<KnowledgeBaseStep onSubmit={onSubmit} />);

      const submitButton = screen.getByRole("button", { name: /save knowledge base/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Please provide either a URL or upload at least one file")).toBeInTheDocument();
      });
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("accepts valid URL format", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<KnowledgeBaseStep onSubmit={onSubmit} />);

      const urlInput = screen.getByLabelText(/add url/i);
      await user.type(urlInput, "https://example.com/docs");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText("Valid URL")).toBeInTheDocument();
        expect(screen.queryByText("Invalid URL format")).not.toBeInTheDocument();
      });
    });
  });

  describe("ToolConfigStep - Validation", () => {
    it("shows error when no tools are selected", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<ToolConfigStep onSubmit={onSubmit} />);

      const submitButton = screen.getByRole("button", { name: /save tools/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Select at least one tool")).toBeInTheDocument();
      });
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("clears error when at least one tool is selected", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<ToolConfigStep onSubmit={onSubmit} />);

      const submitButton = screen.getByRole("button", { name: /save tools/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Select at least one tool")).toBeInTheDocument();
      });

      const firstToolCheckbox = screen.getByLabelText(/web search/i);
      await user.click(firstToolCheckbox);

      await waitFor(() => {
        expect(screen.queryByText("Select at least one tool")).not.toBeInTheDocument();
      });
    });
  });
});
