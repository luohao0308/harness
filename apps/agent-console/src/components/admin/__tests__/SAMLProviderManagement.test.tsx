import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { SAMLProviderList } from "../SAMLProviderList";
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

describe("SAMLProviderList", () => {
  const mockOnEdit = vi.fn();
  const mockOnAdd = vi.fn();
  const mockOnRefresh = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no providers exist", () => {
    render(
      <SAMLProviderList
        providers={[]}
        onEdit={mockOnEdit}
        onAdd={mockOnAdd}
        onRefresh={mockOnRefresh}
      />,
    );

    expect(screen.getByText("No SAML providers configured")).toBeInTheDocument();
    expect(screen.getByText("Add your first provider")).toBeInTheDocument();
  });

  it("renders provider list with correct data", () => {
    render(
      <SAMLProviderList
        providers={[mockProvider]}
        onEdit={mockOnEdit}
        onAdd={mockOnAdd}
        onRefresh={mockOnRefresh}
      />,
    );

    expect(screen.getByText("Test Provider")).toBeInTheDocument();
    expect(screen.getByText("https://app.example.com/saml/metadata")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("calls onEdit when edit button is clicked", async () => {
    const user = userEvent.setup();
    render(
      <SAMLProviderList
        providers={[mockProvider]}
        onEdit={mockOnEdit}
        onAdd={mockOnAdd}
        onRefresh={mockOnRefresh}
      />,
    );

    const editButton = screen.getByTitle("Edit");
    await user.click(editButton);

    expect(mockOnEdit).toHaveBeenCalledWith(mockProvider);
  });

  it("deletes provider after confirmation", async () => {
    const user = userEvent.setup();
    const mockDeleteSAMLProvider = vi.mocked(api.deleteSAMLProvider);
    mockDeleteSAMLProvider.mockResolvedValue(undefined);

    window.confirm = vi.fn(() => true);

    render(
      <SAMLProviderList
        providers={[mockProvider]}
        onEdit={mockOnEdit}
        onAdd={mockOnAdd}
        onRefresh={mockOnRefresh}
      />,
    );

    const deleteButton = screen.getByTitle("Delete");
    await user.click(deleteButton);

    await waitFor(() => {
      expect(mockDeleteSAMLProvider).toHaveBeenCalledWith("provider-1");
      expect(mockOnRefresh).toHaveBeenCalled();
    });
  });

  it("tests connection and displays result", async () => {
    const user = userEvent.setup();
    const mockTestSAMLConnection = vi.mocked(api.testSAMLConnection);
    mockTestSAMLConnection.mockResolvedValue({
      status: "success",
      message: "Connection successful",
    });

    render(
      <SAMLProviderList
        providers={[mockProvider]}
        onEdit={mockOnEdit}
        onAdd={mockOnAdd}
        onRefresh={mockOnRefresh}
      />,
    );

    const testButton = screen.getByTitle("Test Connection");
    await user.click(testButton);

    await waitFor(() => {
      expect(mockTestSAMLConnection).toHaveBeenCalledWith("provider-1");
      expect(screen.getByText("Connection successful")).toBeInTheDocument();
    });
  });
});

describe("SAMLProviderForm", () => {
  const mockOnSuccess = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders form with empty fields for new provider", () => {
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    expect(screen.getByLabelText("Provider Name")).toHaveValue("");
    expect(screen.getByLabelText("Entity ID")).toHaveValue("");
    expect(screen.getByLabelText("SSO URL")).toHaveValue("");
    expect(screen.getByText("Create Provider")).toBeInTheDocument();
  });

  it("renders form with provider data for editing", () => {
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

  it("validates URL format", async () => {
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

  it("submits form with metadata URL", async () => {
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

  it("switches between metadata URL and XML upload", async () => {
    const user = userEvent.setup();
    render(<SAMLProviderForm onSuccess={mockOnSuccess} onCancel={mockOnCancel} />);

    expect(screen.getByPlaceholderText("e.g., https://idp.example.com/metadata.xml")).toBeInTheDocument();

    const uploadXmlButton = screen.getByText("Upload XML");
    await user.click(uploadXmlButton);

    expect(screen.getByText("Choose XML File")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText("e.g., https://idp.example.com/metadata.xml")).not.toBeInTheDocument();

    const metadataUrlButton = screen.getByText("Metadata URL");
    await user.click(metadataUrlButton);

    expect(screen.getByPlaceholderText("e.g., https://idp.example.com/metadata.xml")).toBeInTheDocument();
  });

  it("handles XML file upload", async () => {
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
});
