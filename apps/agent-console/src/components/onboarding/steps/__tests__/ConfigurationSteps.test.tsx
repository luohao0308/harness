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

    const submitButton = screen.getByRole("button", { name: /save configuration/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/api key is required/i)).toBeInTheDocument();
    });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  describe("API Key Validation", () => {
    it("shows error when API key is empty", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const apiKeyInput = screen.getByLabelText(/api key/i);
      await user.click(apiKeyInput);
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText(/api key is required/i)).toBeInTheDocument();
      });
    });

    it("shows success indicator when API key is valid", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const apiKeyInput = screen.getByLabelText(/api key/i);
      await user.type(apiKeyInput, "sk-test123456");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText(/looks good/i)).toBeInTheDocument();
      });
    });

    it("toggles API key visibility", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const apiKeyInput = screen.getByLabelText(/api key/i) as HTMLInputElement;
      expect(apiKeyInput.type).toBe("password");

      const toggleButton = screen.getByLabelText(/show api key/i);
      await user.click(toggleButton);

      expect(apiKeyInput.type).toBe("text");
      expect(screen.getByLabelText(/hide api key/i)).toBeInTheDocument();
    });
  });

  describe("Base URL Validation", () => {
    it("shows error for invalid URL format", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const baseUrlInput = screen.getByLabelText(/base url/i);
      await user.type(baseUrlInput, "not-a-valid-url");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText(/base url must be a valid url/i)).toBeInTheDocument();
      });
    });

    it("shows success indicator for valid URL", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const baseUrlInput = screen.getByLabelText(/base url/i);
      await user.type(baseUrlInput, "https://api.openai.com/v1");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText(/valid url format/i)).toBeInTheDocument();
      });
    });

    it("rejects URL without protocol", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const baseUrlInput = screen.getByLabelText(/base url/i);
      await user.type(baseUrlInput, "api.openai.com");
      await user.tab();

      await waitFor(() => {
        expect(screen.getByText(/base url must be a valid url/i)).toBeInTheDocument();
      });
    });
  });

  describe("Model Selection Validation", () => {
    it("shows error when no model is selected", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/model selection is required/i)).toBeInTheDocument();
      });
    });

    it("renders all available models", () => {
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const modelSelect = screen.getByLabelText(/model/i);
      expect(modelSelect).toBeInTheDocument();

      expect(screen.getByRole("option", { name: /gpt-4/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /gpt-3.5 turbo/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /claude 3 opus/i })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /claude 3 sonnet/i })).toBeInTheDocument();
    });
  });

  describe("Form Submission", () => {
    it("submits form with valid data", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(<ModelProviderStep onSubmit={onSubmit} />);

      await user.type(screen.getByLabelText(/api key/i), "sk-test123456");
      await user.type(screen.getByLabelText(/base url/i), "https://api.openai.com/v1");
      await user.selectOptions(screen.getByLabelText(/model/i), "gpt-4");

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith({
          apiKey: "sk-test123456",
          baseUrl: "https://api.openai.com/v1",
          model: "gpt-4",
        });
      });
    });

    it("shows loading state during submission", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn(() => new Promise((resolve) => setTimeout(resolve, 100)));
      render(<ModelProviderStep onSubmit={onSubmit} />);

      await user.type(screen.getByLabelText(/api key/i), "sk-test123456");
      await user.type(screen.getByLabelText(/base url/i), "https://api.openai.com/v1");
      await user.selectOptions(screen.getByLabelText(/model/i), "gpt-4");

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      expect(screen.getByText(/saving/i)).toBeInTheDocument();
      expect(submitButton).toBeDisabled();
    });

    it("displays error message on submission failure", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn().mockRejectedValue(new Error("Network error"));
      render(<ModelProviderStep onSubmit={onSubmit} />);

      await user.type(screen.getByLabelText(/api key/i), "sk-test123456");
      await user.type(screen.getByLabelText(/base url/i), "https://api.openai.com/v1");
      await user.selectOptions(screen.getByLabelText(/model/i), "gpt-4");

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/network error/i)).toBeInTheDocument();
        expect(screen.getByText(/configuration error/i)).toBeInTheDocument();
      });
    });

    it("displays generic error message for unknown errors", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn().mockRejectedValue("Unknown error");
      render(<ModelProviderStep onSubmit={onSubmit} />);

      await user.type(screen.getByLabelText(/api key/i), "sk-test123456");
      await user.type(screen.getByLabelText(/base url/i), "https://api.openai.com/v1");
      await user.selectOptions(screen.getByLabelText(/model/i), "gpt-4");

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/failed to save configuration/i)).toBeInTheDocument();
      });
    });
  });

  describe("Accessibility", () => {
    it("has proper ARIA labels and descriptions", () => {
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const apiKeyInput = screen.getByLabelText(/api key/i);
      expect(apiKeyInput).toHaveAttribute("aria-invalid", "false");

      const baseUrlInput = screen.getByLabelText(/base url/i);
      expect(baseUrlInput).toHaveAttribute("aria-invalid", "false");
    });

    it("updates aria-invalid when field has error", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        const apiKeyInput = screen.getByLabelText(/api key/i);
        expect(apiKeyInput).toHaveAttribute("aria-invalid", "true");
      });
    });

    it("associates error messages with inputs via aria-describedby", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();
      render(<ModelProviderStep onSubmit={onSubmit} />);

      const submitButton = screen.getByRole("button", { name: /save configuration/i });
      await user.click(submitButton);

      await waitFor(() => {
        const apiKeyInput = screen.getByLabelText(/api key/i);
        expect(apiKeyInput).toHaveAttribute("aria-describedby", "apiKey-error");
      });
    });

    it("marks required fields with aria-label on asterisk", () => {
      const onSubmit = vi.fn();
      const { container } = render(<ModelProviderStep onSubmit={onSubmit} />);

      const requiredMarkers = container.querySelectorAll('[aria-label="required"]');
      expect(requiredMarkers.length).toBeGreaterThan(0);
    });
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
