import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { SAMLProviderForm } from "../SAMLProviderForm";
import type { SAMLProvider } from "../../../features/tasks/api";
import * as api from "../../../features/tasks/api";

vi.mock("../../../features/tasks/api");

const mockProvider: SAMLProvider = {
  id: "provider-1",
  organization_id: "org-1",
  name: "Test Provider",
  entity_id: "https://app.example.com/saml/metadata",
  sso_url: "https://idp.example.com/sso/saml",
  idp_metadata_url: "https://idp.example.com/metadata.xml",
  idp_metadata_xml: null,
  certificate: null,
  status: "active",
  test_connection_status: null,
  test_connection_error: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("SAMLProviderForm", () => {
  const mockOnSuccess = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Form Rendering", () => {
    it("renders form with empty fields for new provider", () => {
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      expect(screen.getByLabelText("Provider Name")).toHaveValue("");
      expect(screen.getByLabelText("Entity ID")).toHaveValue("");
      expect(screen.getByLabelText("SSO URL")).toHaveValue("");
      expect(screen.getByText("Create Provider")).toBeInTheDocument();
    });

    it("renders form with provider data for editing (pre-filled edit mode)", () => {
      render(
        <SAMLProviderForm
          provider={mockProvider}
          onSuccess={mockOnSuccess}
          onCancel={mockOnCancel}
        />,
      );

      expect(screen.getByLabelText("Provider Name")).toHaveValue("Test Provider");
      expect(screen.getByLabelText("Entity ID")).toHaveValue(
        "https://app.example.com/saml/metadata",
      );
      expect(screen.getByLabelText("SSO URL")).toHaveValue("https://idp.example.com/sso/saml");
      expect(screen.getByText("Update Provider")).toBeInTheDocument();
    });
  });

  describe("Field Validation", () => {
    it("validates required fields", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      const submitButton = screen.getByText("Create Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Name is required")).toBeInTheDocument();
        expect(screen.getByText("Entity ID is required")).toBeInTheDocument();
      });
    });

    it("validates URL format for SSO URL", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      const nameInput = screen.getByLabelText("Provider Name");
      const entityIdInput = screen.getByLabelText("Entity ID");
      const ssoUrlInput = screen.getByLabelText("SSO URL");

      await user.type(nameInput, "Test Provider");
      await user.type(entityIdInput, "test-entity-id");
      await user.type(ssoUrlInput, "invalid-url");

      const submitButton = screen.getByText("Create Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Must be a valid URL")).toBeInTheDocument();
      });
    });

    it("validates URL format for metadata URL", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      await user.type(screen.getByLabelText("Provider Name"), "Test Provider");
      await user.type(screen.getByLabelText("Entity ID"), "https://app.example.com/entity");
      await user.type(screen.getByLabelText("SSO URL"), "https://idp.example.com/sso");

      const metadataUrlInput = screen.getByPlaceholderText(
        "e.g., https://idp.example.com/metadata.xml",
      );
      await user.type(metadataUrlInput, "not-a-valid-url");

      const submitButton = screen.getByText("Create Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Must be a valid URL")).toBeInTheDocument();
      });
    });
  });

  describe("Metadata Toggle", () => {
    it("toggles between metadata URL and XML upload modes", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      // Initially should show URL input
      expect(
        screen.getByPlaceholderText("e.g., https://idp.example.com/metadata.xml"),
      ).toBeInTheDocument();

      // Switch to XML mode
      const uploadXmlButton = screen.getByText("Upload XML");
      await user.click(uploadXmlButton);

      expect(screen.getByText("Choose XML File")).toBeInTheDocument();
      expect(
        screen.queryByPlaceholderText("e.g., https://idp.example.com/metadata.xml"),
      ).not.toBeInTheDocument();

      // Switch back to URL mode
      const metadataUrlButton = screen.getByText("Metadata URL");
      await user.click(metadataUrlButton);

      expect(
        screen.getByPlaceholderText("e.g., https://idp.example.com/metadata.xml"),
      ).toBeInTheDocument();
      expect(screen.queryByText("Choose XML File")).not.toBeInTheDocument();
    });
  });

  describe("XML File Upload", () => {
    it("handles XML file upload successfully", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      const uploadXmlButton = screen.getByText("Upload XML");
      await user.click(uploadXmlButton);

      const xmlContent = '<?xml version="1.0"?><EntityDescriptor>test</EntityDescriptor>';
      const file = new File([xmlContent], "metadata.xml", { type: "text/xml" });

      const fileInput = screen.getByLabelText("Choose XML File") as HTMLInputElement;
      await user.upload(fileInput, file);

      await waitFor(() => {
        expect(screen.getByText("metadata.xml")).toBeInTheDocument();
      });
    });

    it("removes uploaded XML file", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      const uploadXmlButton = screen.getByText("Upload XML");
      await user.click(uploadXmlButton);

      const xmlContent = '<?xml version="1.0"?><EntityDescriptor>test</EntityDescriptor>';
      const file = new File([xmlContent], "metadata.xml", { type: "text/xml" });

      const fileInput = screen.getByLabelText("Choose XML File") as HTMLInputElement;
      await user.upload(fileInput, file);

      await waitFor(() => {
        expect(screen.getByText("metadata.xml")).toBeInTheDocument();
      });

      // Remove the file
      const removeButtons = screen.getAllByRole("button");
      const removeButton = removeButtons.find(
        (btn) => btn.querySelector("svg") && btn.textContent === "",
      );
      if (removeButton) {
        await user.click(removeButton);
      }

      await waitFor(() => {
        expect(screen.queryByText("metadata.xml")).not.toBeInTheDocument();
      });
    });
  });

  describe("Form Submission", () => {
    it("submits form successfully with metadata URL", async () => {
      const user = userEvent.setup();
      const mockCreateSAMLProvider = vi.mocked(api.createSAMLProvider);
      mockCreateSAMLProvider.mockResolvedValue(mockProvider);

      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      await user.type(screen.getByLabelText("Provider Name"), "Test Provider");
      await user.type(
        screen.getByLabelText("Entity ID"),
        "https://app.example.com/saml/metadata",
      );
      await user.type(screen.getByLabelText("SSO URL"), "https://idp.example.com/sso/saml");

      const metadataUrlInput = screen.getByPlaceholderText(
        "e.g., https://idp.example.com/metadata.xml",
      );
      await user.type(metadataUrlInput, "https://idp.example.com/metadata.xml");

      const submitButton = screen.getByText("Create Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockCreateSAMLProvider).toHaveBeenCalledWith({
          name: "Test Provider",
          entity_id: "https://app.example.com/saml/metadata",
          sso_url: "https://idp.example.com/sso/saml",
          idp_metadata_url: "https://idp.example.com/metadata.xml",
          idp_metadata_xml: null,
        });
        expect(mockOnSuccess).toHaveBeenCalled();
      });
    });

    it("submits form successfully with XML upload", async () => {
      const user = userEvent.setup();
      const mockCreateSAMLProvider = vi.mocked(api.createSAMLProvider);
      mockCreateSAMLProvider.mockResolvedValue(mockProvider);

      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      await user.type(screen.getByLabelText("Provider Name"), "Test Provider");
      await user.type(
        screen.getByLabelText("Entity ID"),
        "https://app.example.com/saml/metadata",
      );
      await user.type(screen.getByLabelText("SSO URL"), "https://idp.example.com/sso/saml");

      // Switch to XML mode
      const uploadXmlButton = screen.getByText("Upload XML");
      await user.click(uploadXmlButton);

      const xmlContent = '<?xml version="1.0"?><EntityDescriptor>test</EntityDescriptor>';
      const file = new File([xmlContent], "metadata.xml", { type: "text/xml" });

      const fileInput = screen.getByLabelText("Choose XML File") as HTMLInputElement;
      await user.upload(fileInput, file);

      await waitFor(() => {
        expect(screen.getByText("metadata.xml")).toBeInTheDocument();
      });

      const submitButton = screen.getByText("Create Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockCreateSAMLProvider).toHaveBeenCalled();
        expect(mockOnSuccess).toHaveBeenCalled();
      });
    });

    it("handles form submission errors", async () => {
      const user = userEvent.setup();
      const mockCreateSAMLProvider = vi.mocked(api.createSAMLProvider);
      mockCreateSAMLProvider.mockRejectedValue(new Error("Failed to create provider"));

      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      await user.type(screen.getByLabelText("Provider Name"), "Test Provider");
      await user.type(
        screen.getByLabelText("Entity ID"),
        "https://app.example.com/saml/metadata",
      );
      await user.type(screen.getByLabelText("SSO URL"), "https://idp.example.com/sso/saml");

      const submitButton = screen.getByText("Create Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Failed to create provider")).toBeInTheDocument();
      });
    });

    it("updates existing provider successfully", async () => {
      const user = userEvent.setup();
      const mockUpdateSAMLProvider = vi.mocked(api.updateSAMLProvider);
      mockUpdateSAMLProvider.mockResolvedValue({
        ...mockProvider,
        name: "Updated Provider",
      });

      render(
        <SAMLProviderForm
          provider={mockProvider}
          onSuccess={mockOnSuccess}
          onCancel={mockOnCancel}
        />,
      );

      const nameInput = screen.getByLabelText("Provider Name");
      await user.clear(nameInput);
      await user.type(nameInput, "Updated Provider");

      const submitButton = screen.getByText("Update Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockUpdateSAMLProvider).toHaveBeenCalledWith("provider-1", expect.any(Object));
        expect(mockOnSuccess).toHaveBeenCalled();
      });
    });
  });

  describe("User Interactions", () => {
    it("calls onCancel when cancel button is clicked", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      const cancelButton = screen.getByText("Cancel");
      await user.click(cancelButton);

      expect(mockOnCancel).toHaveBeenCalled();
    });

    it("disables buttons while submitting", async () => {
      const user = userEvent.setup();
      const mockCreateSAMLProvider = vi.mocked(api.createSAMLProvider);

      // Make the promise never resolve to test loading state
      mockCreateSAMLProvider.mockImplementation(
        () => new Promise(() => {}),
      );

      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      await user.type(screen.getByLabelText("Provider Name"), "Test Provider");
      await user.type(
        screen.getByLabelText("Entity ID"),
        "https://app.example.com/saml/metadata",
      );
      await user.type(screen.getByLabelText("SSO URL"), "https://idp.example.com/sso/saml");

      const submitButton = screen.getByText("Create Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Saving...")).toBeInTheDocument();
        expect(screen.getByText("Cancel")).toBeDisabled();
      });
    });

    it("clears field errors when user types", async () => {
      const user = userEvent.setup();
      render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

      // Trigger validation errors
      const submitButton = screen.getByText("Create Provider");
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Name is required")).toBeInTheDocument();
      });

      // Type in the field
      const nameInput = screen.getByLabelText("Provider Name");
      await user.type(nameInput, "Test");

      // Error should be cleared
      await waitFor(() => {
        expect(screen.queryByText("Name is required")).not.toBeInTheDocument();
      });
    });
  });
});
