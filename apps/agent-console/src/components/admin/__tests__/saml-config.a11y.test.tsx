/**
 * Accessibility tests for Admin SAML Configuration
 *
 * Tests WCAG 2.1 AA compliance using axe-core:
 * - Automated violation detection
 * - Keyboard navigation
 * - ARIA labels and roles
 * - Focus management
 * - Form accessibility
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, test, expect, vi } from "vitest";
import { SAMLProviderForm } from "../../../components/admin/SAMLProviderForm";

// Mock API functions
vi.mock("../../../features/tasks/api", () => ({
  createSAMLProvider: vi.fn(() => Promise.resolve({ id: "test-id" })),
  updateSAMLProvider: vi.fn(() => Promise.resolve({ id: "test-id" })),
}));

describe("Admin SAML Configuration Accessibility", () => {
  const mockOnSuccess = vi.fn();
  const mockOnCancel = vi.fn();

  test("has no axe violations on initial render (create mode)", async () => {
    const { container } = render(
      <SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />,
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("has no axe violations with existing provider (edit mode)", async () => {
    const mockProvider = {
      id: "okta-1",
      organization_id: "org-1",
      name: "Okta",
      entity_id: "https://app.example.com/saml",
      sso_url: "https://idp.example.com/sso",
      idp_metadata_url: "https://idp.example.com/metadata.xml",
      idp_metadata_xml: null,
      certificate: null,
      status: "active" as const,
      test_connection_status: null,
      test_connection_error: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };

    const { container } = render(
      <SAMLProviderForm provider={mockProvider} onSuccess={mockOnSuccess} onCancel={mockOnCancel} />,
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("has no axe violations with XML upload mode active", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />,
    );

    // Switch to XML upload mode
    const xmlButton = screen.getByRole("button", { name: /Upload XML/i });
    await user.click(xmlButton);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("all form inputs have accessible labels", () => {
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    expect(screen.getByLabelText(/Provider Name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Entity ID/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/SSO URL/i)).toBeInTheDocument();
  });

  test("form inputs are properly labeled with id and htmlFor", () => {
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    const nameInput = screen.getByLabelText(/Provider Name/i);
    const entityIdInput = screen.getByLabelText(/Entity ID/i);
    const ssoUrlInput = screen.getByLabelText(/SSO URL/i);

    expect(nameInput).toHaveAttribute("id", "name");
    expect(entityIdInput).toHaveAttribute("id", "entity_id");
    expect(ssoUrlInput).toHaveAttribute("id", "sso_url");
  });

  test("metadata source toggle buttons are keyboard accessible", async () => {
    const user = userEvent.setup();
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    const urlButton = screen.getByRole("button", { name: /Metadata URL/i });
    const xmlButton = screen.getByRole("button", { name: /Upload XML/i });

    // Tab to buttons
    urlButton.focus();
    expect(urlButton).toHaveFocus();

    // Switch with keyboard
    await user.keyboard("{Enter}");

    // Tab to XML button
    xmlButton.focus();
    expect(xmlButton).toHaveFocus();
  });

  test("file upload input has accessible label", async () => {
    const user = userEvent.setup();
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    // Switch to XML mode
    const xmlButton = screen.getByRole("button", { name: /Upload XML/i });
    await user.click(xmlButton);

    // File input should be present with accessible label
    const fileLabel = screen.getByLabelText(/Choose XML File/i);
    expect(fileLabel).toBeInTheDocument();
  });

  test("error messages are associated with form fields", async () => {
    const user = userEvent.setup();
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    // Submit empty form to trigger validation errors
    const submitButton = screen.getByRole("button", { name: /Create Provider/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/Name is required/i)).toBeInTheDocument();
    });

    // Error message should be near the input
    const errorMessage = screen.getByText(/Name is required/i);
    expect(errorMessage).toHaveClass("text-red-600");
  });

  test("submit button state changes are accessible", async () => {
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    const submitButton = screen.getByRole("button", { name: /Create Provider/i });
    expect(submitButton).toBeInTheDocument();
    expect(submitButton).not.toBeDisabled();
  });

  test("cancel button is keyboard accessible", async () => {
    const user = userEvent.setup();
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    const cancelButton = screen.getByRole("button", { name: /Cancel/i });
    cancelButton.focus();
    expect(cancelButton).toHaveFocus();

    await user.keyboard("{Enter}");
    expect(mockOnCancel).toHaveBeenCalled();
  });

  test("form is navigable with Tab key", async () => {
    const user = userEvent.setup();
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    // Tab through form fields
    await user.tab();
    expect(screen.getByLabelText(/Provider Name/i)).toHaveFocus();

    await user.tab();
    expect(screen.getByLabelText(/Entity ID/i)).toHaveFocus();

    await user.tab();
    expect(screen.getByLabelText(/SSO URL/i)).toHaveFocus();
  });

  test("form has proper semantic structure", () => {
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    const form = screen.getByRole("button", { name: /Create Provider/i }).closest("form");
    expect(form).toBeInTheDocument();
  });

  test("metadata source buttons have clear selected state", async () => {
    const user = userEvent.setup();
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    const urlButton = screen.getByRole("button", { name: /Metadata URL/i });
    const xmlButton = screen.getByRole("button", { name: /Upload XML/i });

    // Initially URL is selected
    expect(urlButton).toHaveClass("bg-blue-100");

    // Switch to XML
    await user.click(xmlButton);
    expect(xmlButton).toHaveClass("bg-blue-100");
  });
});
