import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { SAMLProviderList } from "../SAMLProviderList";
import type { SAMLProvider } from "../../../features/tasks/api";
import * as api from "../../../features/tasks/api";

vi.mock("../../../features/tasks/api");

const mockProviders: SAMLProvider[] = [
  {
    id: "provider-1",
    organization_id: "org-1",
    name: "Okta Provider",
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
  },
  {
    id: "provider-2",
    organization_id: "org-1",
    name: "Azure AD Provider",
    entity_id: "https://app.example.com/saml/azure",
    sso_url: "https://azure.example.com/sso",
    idp_metadata_url: null,
    idp_metadata_xml: "<xml>test</xml>",
    certificate: null,
    status: "inactive",
    test_connection_status: null,
    test_connection_error: null,
    created_at: "2024-01-02T00:00:00Z",
    updated_at: "2024-01-02T00:00:00Z",
  },
  {
    id: "provider-3",
    organization_id: "org-1",
    name: "Testing Provider",
    entity_id: "https://app.example.com/saml/test",
    sso_url: "https://test.example.com/sso",
    idp_metadata_url: "https://test.example.com/metadata.xml",
    idp_metadata_xml: null,
    certificate: null,
    status: "testing",
    test_connection_status: null,
    test_connection_error: null,
    created_at: "2024-01-03T00:00:00Z",
    updated_at: "2024-01-03T00:00:00Z",
  },
];

describe("SAMLProviderList", () => {
  const mockOnEdit = vi.fn();
  const mockOnAdd = vi.fn();
  const mockOnRefresh = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    window.confirm = vi.fn();
    window.alert = vi.fn();
  });

  describe("List Rendering", () => {
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
          providers={mockProviders}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      expect(screen.getByText("Okta Provider")).toBeInTheDocument();
      expect(screen.getByText("Azure AD Provider")).toBeInTheDocument();
      expect(screen.getByText("Testing Provider")).toBeInTheDocument();
      expect(screen.getByText("https://app.example.com/saml/metadata")).toBeInTheDocument();
    });

    it("displays provider status badges correctly", () => {
      render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      // Check for all status badges
      expect(screen.getByText("active")).toBeInTheDocument();
      expect(screen.getByText("inactive")).toBeInTheDocument();
      expect(screen.getByText("testing")).toBeInTheDocument();
    });

    it("formats dates correctly", () => {
      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      // The date should be formatted as "Jan 1, 2024, 12:00 AM" or similar
      expect(screen.getByText(/Jan.*2024/)).toBeInTheDocument();
    });

    it("displays truncated SSO URLs with title attribute", () => {
      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const ssoUrlElement = screen.getByText("https://idp.example.com/sso/saml");
      expect(ssoUrlElement).toHaveAttribute("title", "https://idp.example.com/sso/saml");
    });
  });

  describe("User Actions", () => {
    it("calls onAdd when add button is clicked", async () => {
      const user = userEvent.setup();
      render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const addButton = screen.getByText("Add Provider");
      await user.click(addButton);

      expect(mockOnAdd).toHaveBeenCalled();
    });

    it("calls onAdd when clicking 'Add your first provider' in empty state", async () => {
      const user = userEvent.setup();
      render(
        <SAMLProviderList
          providers={[]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const addButton = screen.getByText("Add your first provider");
      await user.click(addButton);

      expect(mockOnAdd).toHaveBeenCalled();
    });

    it("calls onEdit when edit button is clicked", async () => {
      const user = userEvent.setup();
      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const editButton = screen.getByTitle("Edit");
      await user.click(editButton);

      expect(mockOnEdit).toHaveBeenCalledWith(mockProviders[0]);
    });
  });

  describe("Delete Functionality", () => {
    it("deletes provider after confirmation", async () => {
      const user = userEvent.setup();
      const mockDeleteSAMLProvider = vi.mocked(api.deleteSAMLProvider);
      mockDeleteSAMLProvider.mockResolvedValue(undefined);

      vi.mocked(window.confirm).mockReturnValue(true);

      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const deleteButton = screen.getByTitle("Delete");
      await user.click(deleteButton);

      await waitFor(() => {
        expect(window.confirm).toHaveBeenCalledWith(
          "Are you sure you want to delete this SAML provider?",
        );
        expect(mockDeleteSAMLProvider).toHaveBeenCalledWith("provider-1");
        expect(mockOnRefresh).toHaveBeenCalled();
      });
    });

    it("does not delete provider when confirmation is cancelled", async () => {
      const user = userEvent.setup();
      const mockDeleteSAMLProvider = vi.mocked(api.deleteSAMLProvider);

      vi.mocked(window.confirm).mockReturnValue(false);

      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const deleteButton = screen.getByTitle("Delete");
      await user.click(deleteButton);

      await waitFor(() => {
        expect(window.confirm).toHaveBeenCalled();
        expect(mockDeleteSAMLProvider).not.toHaveBeenCalled();
        expect(mockOnRefresh).not.toHaveBeenCalled();
      });
    });

    it("handles delete errors", async () => {
      const user = userEvent.setup();
      const mockDeleteSAMLProvider = vi.mocked(api.deleteSAMLProvider);
      mockDeleteSAMLProvider.mockRejectedValue(new Error("Failed to delete provider"));

      vi.mocked(window.confirm).mockReturnValue(true);

      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const deleteButton = screen.getByTitle("Delete");
      await user.click(deleteButton);

      await waitFor(() => {
        expect(mockDeleteSAMLProvider).toHaveBeenCalled();
        expect(window.alert).toHaveBeenCalledWith("Failed to delete provider");
      });
    });

    it("disables delete button while deleting", async () => {
      const user = userEvent.setup();
      const mockDeleteSAMLProvider = vi.mocked(api.deleteSAMLProvider);

      // Make the promise never resolve to test loading state
      mockDeleteSAMLProvider.mockImplementation(() => new Promise(() => {}));
      vi.mocked(window.confirm).mockReturnValue(true);

      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const deleteButton = screen.getByTitle("Delete");
      await user.click(deleteButton);

      await waitFor(() => {
        expect(deleteButton).toBeDisabled();
      });
    });
  });

  describe("Test Connection Functionality", () => {
    it("tests connection and displays success result", async () => {
      const user = userEvent.setup();
      const mockTestSAMLConnection = vi.mocked(api.testSAMLConnection);
      mockTestSAMLConnection.mockResolvedValue({
        status: "success",
        message: "Connection successful",
      });

      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
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
        expect(mockOnRefresh).toHaveBeenCalled();
      });
    });

    it("tests connection and displays failure result", async () => {
      const user = userEvent.setup();
      const mockTestSAMLConnection = vi.mocked(api.testSAMLConnection);
      mockTestSAMLConnection.mockResolvedValue({
        status: "failed",
        message: "Connection failed",
        error: "Invalid certificate",
      });

      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const testButton = screen.getByTitle("Test Connection");
      await user.click(testButton);

      await waitFor(() => {
        expect(mockTestSAMLConnection).toHaveBeenCalledWith("provider-1");
        expect(screen.getByText("Invalid certificate")).toBeInTheDocument();
      });
    });

    it("handles test connection errors", async () => {
      const user = userEvent.setup();
      const mockTestSAMLConnection = vi.mocked(api.testSAMLConnection);
      mockTestSAMLConnection.mockRejectedValue(new Error("Network error"));

      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const testButton = screen.getByTitle("Test Connection");
      await user.click(testButton);

      await waitFor(() => {
        expect(mockTestSAMLConnection).toHaveBeenCalledWith("provider-1");
        expect(screen.getByText("Network error")).toBeInTheDocument();
      });
    });

    it("displays testing state while connection test is in progress", async () => {
      const user = userEvent.setup();
      const mockTestSAMLConnection = vi.mocked(api.testSAMLConnection);

      // Make the promise never resolve to test loading state
      mockTestSAMLConnection.mockImplementation(() => new Promise(() => {}));

      render(
        <SAMLProviderList
          providers={[mockProviders[0]]}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const testButton = screen.getByTitle("Test Connection");
      await user.click(testButton);

      await waitFor(() => {
        expect(screen.getByText("Testing connection...")).toBeInTheDocument();
        expect(testButton).toBeDisabled();
      });
    });

    it("allows testing multiple providers independently", async () => {
      const user = userEvent.setup();
      const mockTestSAMLConnection = vi.mocked(api.testSAMLConnection);
      mockTestSAMLConnection.mockResolvedValue({
        status: "success",
        message: "Connection successful",
      });

      render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      const testButtons = screen.getAllByTitle("Test Connection");

      // Test first provider
      await user.click(testButtons[0]);

      await waitFor(() => {
        expect(mockTestSAMLConnection).toHaveBeenCalledWith("provider-1");
      });

      // Test second provider
      await user.click(testButtons[1]);

      await waitFor(() => {
        expect(mockTestSAMLConnection).toHaveBeenCalledWith("provider-2");
      });

      expect(mockTestSAMLConnection).toHaveBeenCalledTimes(2);
    });
  });

  describe("Multiple Providers", () => {
    it("renders all providers with correct action buttons", () => {
      render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      // Should have 3 edit buttons (one per provider)
      const editButtons = screen.getAllByTitle("Edit");
      expect(editButtons).toHaveLength(3);

      // Should have 3 delete buttons
      const deleteButtons = screen.getAllByTitle("Delete");
      expect(deleteButtons).toHaveLength(3);

      // Should have 3 test connection buttons
      const testButtons = screen.getAllByTitle("Test Connection");
      expect(testButtons).toHaveLength(3);
    });

    it("handles actions on specific provider in list", async () => {
      const user = userEvent.setup();
      render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={mockOnEdit}
          onAdd={mockOnAdd}
          onRefresh={mockOnRefresh}
        />,
      );

      // Click edit on the second provider
      const editButtons = screen.getAllByTitle("Edit");
      await user.click(editButtons[1]);

      expect(mockOnEdit).toHaveBeenCalledWith(mockProviders[1]);
    });
  });
});
