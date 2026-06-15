/**
 * Accessibility tests for Tables
 *
 * Tests WCAG 2.1 AA compliance using axe-core:
 * - Automated violation detection
 * - Keyboard navigation
 * - ARIA labels and roles
 * - Table semantics
 * - Screen reader compatibility
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, test, expect, vi } from "vitest";
import { Table, Th, Td } from "../../../components/ui/table";
import { SAMLProviderList } from "../../../components/admin/SAMLProviderList";
import type { SAMLProvider } from "../../../features/tasks/api";

// Mock API functions
vi.mock("../../../features/tasks/api", () => ({
  deleteSAMLProvider: vi.fn(() => Promise.resolve()),
  testSAMLConnection: vi.fn(() =>
    Promise.resolve({
      status: "success",
      message: "Connection successful",
    }),
  ),
}));

describe("Tables Accessibility", () => {
  describe("Basic Table Component", () => {
    test("has no axe violations with proper table structure", async () => {
      const { container } = render(
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Email</Th>
              <Th>Role</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>John Doe</Td>
              <Td>john@example.com</Td>
              <Td>Admin</Td>
            </tr>
            <tr>
              <Td>Jane Smith</Td>
              <Td>jane@example.com</Td>
              <Td>User</Td>
            </tr>
          </tbody>
        </Table>,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("table headers are properly marked", () => {
      render(
        <Table>
          <thead>
            <tr>
              <Th>Column 1</Th>
              <Th>Column 2</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>Data 1</Td>
              <Td>Data 2</Td>
            </tr>
          </tbody>
        </Table>,
      );

      const headers = screen.getAllByRole("columnheader");
      expect(headers).toHaveLength(2);
      expect(headers[0]).toHaveTextContent("Column 1");
      expect(headers[1]).toHaveTextContent("Column 2");
    });

    test("table cells are accessible", () => {
      render(
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>Test Name</Td>
            </tr>
          </tbody>
        </Table>,
      );

      const cells = screen.getAllByRole("cell");
      expect(cells.length).toBeGreaterThan(0);
    });
  });

  describe("SAMLProviderList Table", () => {
    const mockProviders: SAMLProvider[] = [
      {
        id: "okta-1",
        name: "Okta",
        entity_id: "https://app.example.com/saml",
        sso_url: "https://idp.example.com/sso",
        idp_metadata_url: "https://idp.example.com/metadata.xml",
        idp_metadata_xml: null,
        enabled: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "azure-1",
        name: "Azure AD",
        entity_id: "https://app.example.com/saml",
        sso_url: "https://login.microsoftonline.com/sso",
        idp_metadata_url: null,
        idp_metadata_xml: "<xml>...</xml>",
        enabled: true,
        created_at: "2026-01-02T00:00:00Z",
        updated_at: "2026-01-02T00:00:00Z",
      },
    ];

    test("has no axe violations with provider list", async () => {
      const { container } = render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={vi.fn()}
          onAdd={vi.fn()}
          onRefresh={vi.fn()}
        />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("has no axe violations with empty state", async () => {
      const { container } = render(
        <SAMLProviderList
          providers={[]}
          onEdit={vi.fn()}
          onAdd={vi.fn()}
          onRefresh={vi.fn()}
        />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("table has proper semantic structure", () => {
      render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={vi.fn()}
          onAdd={vi.fn()}
          onRefresh={vi.fn()}
        />,
      );

      const table = screen.getByRole("table");
      expect(table).toBeInTheDocument();

      const columnHeaders = screen.getAllByRole("columnheader");
      expect(columnHeaders.length).toBeGreaterThan(0);
    });

    test("action buttons in table are keyboard accessible", async () => {
      const user = userEvent.setup();
      const onEdit = vi.fn();

      render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={onEdit}
          onAdd={vi.fn()}
          onRefresh={vi.fn()}
        />,
      );

      const buttons = screen.getAllByRole("button");
      const editButtons = buttons.filter((btn) => btn.getAttribute("aria-label")?.includes("Edit"));

      if (editButtons.length > 0) {
        editButtons[0].focus();
        expect(editButtons[0]).toHaveFocus();
      }
    });

    test("add provider button is accessible", async () => {
      const user = userEvent.setup();
      const onAdd = vi.fn();

      render(
        <SAMLProviderList
          providers={mockProviders}
          onEdit={vi.fn()}
          onAdd={onAdd}
          onRefresh={vi.fn()}
        />,
      );

      const addButton = screen.getByRole("button", { name: /Add Provider/i });
      expect(addButton).toBeInTheDocument();

      addButton.focus();
      expect(addButton).toHaveFocus();

      await user.keyboard("{Enter}");
      expect(onAdd).toHaveBeenCalled();
    });

    test("empty state button is accessible", async () => {
      const user = userEvent.setup();
      const onAdd = vi.fn();

      render(
        <SAMLProviderList providers={[]} onEdit={vi.fn()} onAdd={onAdd} onRefresh={vi.fn()} />,
      );

      const addButton = screen.getByRole("button", { name: /Add your first provider/i });
      expect(addButton).toBeInTheDocument();

      await user.click(addButton);
      expect(onAdd).toHaveBeenCalled();
    });
  });

  describe("Table Navigation", () => {
    test("table rows are keyboard navigable", async () => {
      const user = userEvent.setup();
      render(
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Action</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>Item 1</Td>
              <Td>
                <button>Edit</button>
              </Td>
            </tr>
            <tr>
              <Td>Item 2</Td>
              <Td>
                <button>Edit</button>
              </Td>
            </tr>
          </tbody>
        </Table>,
      );

      const buttons = screen.getAllByRole("button");

      // Tab to first button
      await user.tab();
      expect(buttons[0]).toHaveFocus();

      // Tab to second button
      await user.tab();
      expect(buttons[1]).toHaveFocus();
    });

    test("table with sortable headers has accessible sort controls", () => {
      render(
        <Table>
          <thead>
            <tr>
              <Th>
                <button aria-label="Sort by name">Name</button>
              </Th>
              <Th>
                <button aria-label="Sort by date">Date</button>
              </Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>Test</Td>
              <Td>2026-01-01</Td>
            </tr>
          </tbody>
        </Table>,
      );

      const sortButtons = screen.getAllByRole("button");
      expect(sortButtons[0]).toHaveAccessibleName(/Sort by name/i);
      expect(sortButtons[1]).toHaveAccessibleName(/Sort by date/i);
    });
  });

  describe("Screen Reader Support", () => {
    test("table has meaningful headers for screen readers", () => {
      render(
        <Table>
          <thead>
            <tr>
              <Th>Provider Name</Th>
              <Th>Status</Th>
              <Th>Actions</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>Okta</Td>
              <Td>Active</Td>
              <Td>
                <button>Edit</button>
              </Td>
            </tr>
          </tbody>
        </Table>,
      );

      const headers = screen.getAllByRole("columnheader");
      expect(headers[0]).toHaveTextContent("Provider Name");
      expect(headers[1]).toHaveTextContent("Status");
      expect(headers[2]).toHaveTextContent("Actions");
    });

    test("table data cells are properly structured", () => {
      render(
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>Test Data</Td>
            </tr>
          </tbody>
        </Table>,
      );

      const cells = screen.getAllByRole("cell");
      expect(cells[0]).toHaveTextContent("Test Data");
    });
  });

  describe("Table Caption", () => {
    test("table with caption has accessible description", () => {
      render(
        <Table>
          <caption className="sr-only">List of SAML providers</caption>
          <thead>
            <tr>
              <Th>Name</Th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <Td>Okta</Td>
            </tr>
          </tbody>
        </Table>,
      );

      const caption = screen.getByText(/List of SAML providers/i);
      expect(caption).toBeInTheDocument();
    });
  });
});
