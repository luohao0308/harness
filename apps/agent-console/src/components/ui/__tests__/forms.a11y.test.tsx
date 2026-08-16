/**
 * Accessibility tests for Forms
 *
 * Tests WCAG 2.1 AA compliance using axe-core:
 * - Automated violation detection
 * - Keyboard navigation
 * - ARIA labels and roles
 * - Focus management
 * - Form validation
 * - Error handling
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, test, expect, vi } from "vitest";
import { Input, Textarea } from "../../../components/ui/input";
import { SAMLProviderForm } from "../../../components/admin/SAMLProviderForm";
import { NotificationChannelForm } from "../../../features/observability/components/NotificationChannelForm";

// Mock API functions
vi.mock("../../../features/tasks/api", () => ({
  createSAMLProvider: vi.fn(() => Promise.resolve({ id: "test-id" })),
  updateSAMLProvider: vi.fn(() => Promise.resolve({ id: "test-id" })),
}));

describe("Forms Accessibility", () => {
  describe("Input Component", () => {
    test("has no axe violations with basic input", async () => {
      const { container } = render(
        <div>
          <label htmlFor="test-input">Test Input</label>
          <Input id="test-input" type="text" />
        </div>,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("has no axe violations with required input", async () => {
      const { container } = render(
        <div>
          <label htmlFor="required-input">Required Input</label>
          <Input id="required-input" type="text" required />
        </div>,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("input is keyboard accessible", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(
        <div>
          <label htmlFor="keyboard-input">Keyboard Input</label>
          <Input id="keyboard-input" type="text" onChange={onChange} />
        </div>,
      );

      const input = screen.getByLabelText(/Keyboard Input/i);
      await user.click(input);
      expect(input).toHaveFocus();

      await user.type(input, "test");
      expect(onChange).toHaveBeenCalled();
    });

    test("input with placeholder has accessible label", () => {
      render(
        <div>
          <label htmlFor="placeholder-input">Email</label>
          <Input id="placeholder-input" type="email" placeholder="user@example.com" />
        </div>,
      );

      const input = screen.getByLabelText(/Email/i);
      expect(input).toHaveAttribute("placeholder", "user@example.com");
    });
  });

  describe("Textarea Component", () => {
    test("has no axe violations with textarea", async () => {
      const { container } = render(
        <div>
          <label htmlFor="test-textarea">Description</label>
          <Textarea id="test-textarea" />
        </div>,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("textarea is keyboard accessible", async () => {
      const user = userEvent.setup();
      const onChange = vi.fn();

      render(
        <div>
          <label htmlFor="keyboard-textarea">Comments</label>
          <Textarea id="keyboard-textarea" onChange={onChange} />
        </div>,
      );

      const textarea = screen.getByLabelText(/Comments/i);
      await user.click(textarea);
      expect(textarea).toHaveFocus();

      await user.type(textarea, "test comment");
      expect(onChange).toHaveBeenCalled();
    });
  });

  describe("SAMLProviderForm", () => {
    test("has no axe violations on form render", async () => {
      const { container } = render(
        <SAMLProviderForm onSuccess={vi.fn()} onCancel={vi.fn()} />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("all form inputs are properly labeled", () => {
      render(<SAMLProviderForm onSuccess={vi.fn()} onCancel={vi.fn()} />);

      expect(screen.getByLabelText(/Provider Name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Entity ID/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/SSO URL/i)).toBeInTheDocument();
    });

    test("form validation errors are accessible", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={vi.fn()} onCancel={vi.fn()} />);

      const submitButton = screen.getByRole("button", { name: /Create Provider/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Name is required/i)).toBeInTheDocument();
      });

      // Error message should be near the input
      const errorMessage = screen.getByText(/Name is required/i);
      expect(errorMessage).toHaveClass("text-red-600");
    });

    test("form inputs are keyboard navigable", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={vi.fn()} onCancel={vi.fn()} />);

      // Tab through form fields
      await user.tab();
      expect(screen.getByLabelText(/Provider Name/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText(/Entity ID/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText(/SSO URL/i)).toHaveFocus();
    });
  });

  describe("NotificationChannelForm", () => {
    test("has no axe violations on form render", async () => {
      const { container } = render(
        <NotificationChannelForm onSubmit={vi.fn()} onCancel={vi.fn()} />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("select dropdown is accessible", () => {
      render(<NotificationChannelForm onSubmit={vi.fn()} onCancel={vi.fn()} />);

      const select = screen.getByRole("combobox");
      expect(select).toBeInTheDocument();
    });

    test("checkbox is accessible", () => {
      render(<NotificationChannelForm onSubmit={vi.fn()} onCancel={vi.fn()} />);

      const checkbox = screen.getByRole("checkbox");
      expect(checkbox).toBeInTheDocument();
    });

    test("form submission with keyboard", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<NotificationChannelForm onSubmit={onSubmit} onCancel={vi.fn()} />);

      const submitButton = screen.getByRole("button", { name: /保存/i });
      submitButton.focus();
      expect(submitButton).toHaveFocus();

      await user.keyboard("{Enter}");
      expect(onSubmit).toHaveBeenCalled();
    });
  });

  describe("Form Focus Management", () => {
    test("focus visible on form elements", async () => {
      const user = userEvent.setup();
      render(
        <form>
          <label htmlFor="focus-input">Name</label>
          <Input id="focus-input" type="text" />
          <button type="submit">Submit</button>
        </form>,
      );

      const input = screen.getByLabelText(/Name/i);
      await user.tab();
      expect(input).toHaveFocus();
    });

    test("tab order is logical", async () => {
      const user = userEvent.setup();
      render(
        <form>
          <label htmlFor="input1">First</label>
          <Input id="input1" type="text" />
          <label htmlFor="input2">Second</label>
          <Input id="input2" type="text" />
          <button type="submit">Submit</button>
        </form>,
      );

      await user.tab();
      expect(screen.getByLabelText(/First/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText(/Second/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByRole("button")).toHaveFocus();
    });
  });

  describe("Required Fields", () => {
    test("required attribute is present on required fields", () => {
      render(
        <form>
          <label htmlFor="required-field">Required Field</label>
          <Input id="required-field" type="text" required />
        </form>,
      );

      const input = screen.getByLabelText(/Required Field/i);
      expect(input).toHaveAttribute("required");
    });

    test("form does not submit when required fields are empty", async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn((e) => e.preventDefault());

      render(
        <form onSubmit={onSubmit}>
          <label htmlFor="required-name">Name</label>
          <Input id="required-name" type="text" required />
          <button type="submit">Submit</button>
        </form>,
      );

      const submitButton = screen.getByRole("button", { name: /Submit/i });
      await user.click(submitButton);

      // Browser validation will prevent submission
      const input = screen.getByLabelText(/Name/i);
      expect(input).toBeInvalid();
    });
  });

  describe("Error Messages", () => {
    test("error messages are associated with inputs", async () => {
      const user = userEvent.setup();
      render(
        <div>
          <label htmlFor="email-input">Email</label>
          <Input id="email-input" type="email" aria-invalid="true" aria-describedby="email-error" />
          <div id="email-error" className="text-red-600">
            Please enter a valid email
          </div>
        </div>,
      );

      const input = screen.getByLabelText(/Email/i);
      expect(input).toHaveAttribute("aria-invalid", "true");
      expect(input).toHaveAttribute("aria-describedby", "email-error");

      const errorMessage = screen.getByText(/Please enter a valid email/i);
      expect(errorMessage).toBeInTheDocument();
    });
  });

  describe("Autocomplete Attributes", () => {
    test("email input has autocomplete attribute", () => {
      render(
        <div>
          <label htmlFor="email">Email</label>
          <Input id="email" type="email" autoComplete="email" />
        </div>,
      );

      const input = screen.getByLabelText(/Email/i);
      expect(input).toHaveAttribute("autocomplete", "email");
    });

    test("password input has autocomplete attribute", () => {
      render(
        <div>
          <label htmlFor="password">Password</label>
          <Input id="password" type="password" autoComplete="current-password" />
        </div>,
      );

      const input = screen.getByLabelText(/Password/i);
      expect(input).toHaveAttribute("autocomplete", "current-password");
    });
  });

  describe("Disabled States", () => {
    test("disabled inputs are properly marked", () => {
      render(
        <div>
          <label htmlFor="disabled-input">Disabled Input</label>
          <Input id="disabled-input" type="text" disabled />
        </div>,
      );

      const input = screen.getByLabelText(/Disabled Input/i);
      expect(input).toBeDisabled();
    });

    test("disabled buttons are properly marked", () => {
      render(<button disabled>Disabled Button</button>);

      const button = screen.getByRole("button");
      expect(button).toBeDisabled();
    });
  });
});
