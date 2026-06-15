/**
 * E2E Test: Admin SAML Configuration
 *
 * Tests the complete CRUD operations for SAML provider management in the admin SSO settings page.
 * Covers: Create, Read, Update, Delete, Test Connection, and Form Validation.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

const API_RE = /http:\/\/(?:127\.0\.0\.1|localhost):(?:8000|5177|15174)\/api\/.*/;

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockSAMLProviders = [
  {
    id: "provider-1",
    organization_id: "org-1",
    name: "Okta",
    entity_id: "https://app.example.com/saml/metadata",
    sso_url: "https://okta.example.com/sso/saml",
    idp_metadata_url: "https://okta.example.com/metadata.xml",
    idp_metadata_xml: null,
    certificate: null,
    status: "active" as const,
    test_connection_status: "success" as const,
    test_connection_error: null,
    created_at: "2024-01-15T10:00:00Z",
    updated_at: "2024-01-15T10:00:00Z",
  },
  {
    id: "provider-2",
    organization_id: "org-1",
    name: "Azure AD",
    entity_id: "https://app.example.com/saml/azure",
    sso_url: "https://login.microsoftonline.com/sso",
    idp_metadata_url: null,
    idp_metadata_xml: "<?xml version=\"1.0\"?><EntityDescriptor>...</EntityDescriptor>",
    certificate: null,
    status: "inactive" as const,
    test_connection_status: null,
    test_connection_error: null,
    created_at: "2024-01-16T10:00:00Z",
    updated_at: "2024-01-16T10:00:00Z",
  },
];

const newProvider = {
  id: "provider-3",
  organization_id: "org-1",
  name: "OneLogin",
  entity_id: "https://app.example.com/saml/onelogin",
  sso_url: "https://onelogin.example.com/sso",
  idp_metadata_url: "https://onelogin.example.com/metadata.xml",
  idp_metadata_xml: null,
  certificate: null,
  status: "active" as const,
  test_connection_status: null,
  test_connection_error: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

// ---------------------------------------------------------------------------
// Mock Setup
// ---------------------------------------------------------------------------

async function setupMocks(page: Page) {
  let providers = [...mockSAMLProviders];

  await page.route(API_RE, async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    // List SAML providers
    if (url.pathname === "/api/auth/saml/providers" && method === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(providers) });
      return;
    }

    // Create SAML provider
    if (url.pathname === "/api/auth/saml/providers" && method === "POST") {
      const payload = request.postDataJSON();
      const created = {
        ...newProvider,
        name: payload.name,
        entity_id: payload.entity_id,
        sso_url: payload.sso_url,
        idp_metadata_url: payload.idp_metadata_url ?? null,
        idp_metadata_xml: payload.idp_metadata_xml ?? null,
      };
      providers.push(created);
      await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(created) });
      return;
    }

    // Update SAML provider
    if (url.pathname.match(/^\/api\/auth\/saml\/providers\/[^/]+$/) && method === "PATCH") {
      const providerId = url.pathname.split("/").pop();
      const payload = request.postDataJSON();
      const index = providers.findIndex((p) => p.id === providerId);
      if (index !== -1) {
        providers[index] = {
          ...providers[index],
          ...payload,
          updated_at: new Date().toISOString(),
        };
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(providers[index]),
        });
      } else {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "Not found" }) });
      }
      return;
    }

    // Delete SAML provider
    if (url.pathname.match(/^\/api\/auth\/saml\/providers\/[^/]+$/) && method === "DELETE") {
      const providerId = url.pathname.split("/").pop();
      providers = providers.filter((p) => p.id !== providerId);
      await route.fulfill({ status: 204 });
      return;
    }

    // Test SAML connection
    if (url.pathname.match(/^\/api\/auth\/saml\/providers\/[^/]+\/test$/) && method === "POST") {
      const providerId = url.pathname.split("/").slice(-2)[0];
      const provider = providers.find((p) => p.id === providerId);
      if (provider) {
        const result = {
          status: "success" as const,
          message: "SAML connection test successful",
        };
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(result) });
      } else {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: "Not found" }) });
      }
      return;
    }

    await route.continue();
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Admin SAML Configuration", () => {
  test.beforeEach(async ({ page }) => {
    await setupMocks(page);
    await page.goto("/admin/sso-settings");
    await page.waitForLoadState("networkidle");
  });

  test("should display existing SAML providers", async ({ page }) => {
    // Wait for providers to load
    await expect(page.getByText("SSO Settings")).toBeVisible();
    await expect(page.getByText("Okta")).toBeVisible();
    await expect(page.getByText("Azure AD")).toBeVisible();

    // Verify provider details
    await expect(page.getByText("https://app.example.com/saml/metadata")).toBeVisible();
    await expect(page.getByText("https://okta.example.com/sso/saml")).toBeVisible();

    // Verify status badges
    await expect(page.locator('text="active"').first()).toBeVisible();
    await expect(page.locator('text="inactive"').first()).toBeVisible();
  });

  test("should add a new SAML provider", async ({ page }) => {
    // Click Add Provider button
    await page.getByRole("button", { name: /Add Provider/i }).click();

    // Wait for dialog to open
    await expect(page.getByText("Add SAML Provider")).toBeVisible();

    // Fill in the form
    await page.getByLabel("Provider Name").fill("OneLogin");
    await page.getByLabel("Entity ID").fill("https://app.example.com/saml/onelogin");
    await page.getByLabel("SSO URL").fill("https://onelogin.example.com/sso");

    // Select Metadata URL option (should be selected by default)
    await page.getByRole("button", { name: /Metadata URL/i }).click();
    await page.getByLabel("IdP Metadata").fill("https://onelogin.example.com/metadata.xml");

    // Submit form
    await page.getByRole("button", { name: /Create Provider/i }).click();

    // Wait for dialog to close and provider to appear
    await expect(page.getByText("Add SAML Provider")).not.toBeVisible();
    await expect(page.getByText("OneLogin")).toBeVisible();
  });

  test("should edit an existing SAML provider", async ({ page }) => {
    // Wait for providers to load
    await expect(page.getByText("Okta")).toBeVisible();

    // Click edit button for Okta provider (first edit button in the table)
    const editButtons = page.getByRole("button", { name: "Edit" });
    await editButtons.first().click();

    // Wait for dialog to open
    await expect(page.getByText("Edit SAML Provider")).toBeVisible();

    // Verify pre-filled values
    await expect(page.getByLabel("Provider Name")).toHaveValue("Okta");

    // Update the name
    await page.getByLabel("Provider Name").fill("Okta Updated");

    // Submit form
    await page.getByRole("button", { name: /Update Provider/i }).click();

    // Wait for dialog to close and updated name to appear
    await expect(page.getByText("Edit SAML Provider")).not.toBeVisible();
    await expect(page.getByText("Okta Updated")).toBeVisible();
  });

  test("should delete a SAML provider", async ({ page }) => {
    // Wait for providers to load
    await expect(page.getByText("Azure AD")).toBeVisible();

    // Mock the confirm dialog
    page.on("dialog", (dialog) => dialog.accept());

    // Click delete button for Azure AD provider (second delete button)
    const deleteButtons = page.locator('button[title="Delete"]');
    await deleteButtons.nth(1).click();

    // Wait for provider to be removed
    await expect(page.getByText("Azure AD")).not.toBeVisible();
    await expect(page.getByText("Okta")).toBeVisible(); // Other provider still exists
  });

  test("should test SAML connection", async ({ page }) => {
    // Wait for providers to load
    await expect(page.getByText("Okta")).toBeVisible();

    // Click test connection button for Okta provider
    const testButtons = page.locator('button[title="Test Connection"]');
    await testButtons.first().click();

    // Wait for test result to appear
    await expect(page.getByText("SAML connection test successful")).toBeVisible({ timeout: 10000 });
  });

  test("should validate form inputs", async ({ page }) => {
    // Click Add Provider button
    await page.getByRole("button", { name: /Add Provider/i }).click();

    // Wait for dialog to open
    await expect(page.getByText("Add SAML Provider")).toBeVisible();

    // Try to submit empty form
    await page.getByRole("button", { name: /Create Provider/i }).click();

    // Verify validation errors
    await expect(page.getByText("Name is required")).toBeVisible();
    await expect(page.getByText("Entity ID is required")).toBeVisible();

    // Fill in name and entity ID
    await page.getByLabel("Provider Name").fill("Test Provider");
    await page.getByLabel("Entity ID").fill("https://app.example.com/test");

    // Fill in invalid SSO URL
    await page.getByLabel("SSO URL").fill("not-a-url");
    await page.getByRole("button", { name: /Create Provider/i }).click();

    // Verify URL validation error
    await expect(page.getByText("Must be a valid URL")).toBeVisible();

    // Fix the URL
    await page.getByLabel("SSO URL").fill("https://test.example.com/sso");

    // Now form should submit successfully
    await page.getByRole("button", { name: /Create Provider/i }).click();
    await expect(page.getByText("Add SAML Provider")).not.toBeVisible();
  });

  test("should switch between metadata URL and XML upload", async ({ page }) => {
    // Click Add Provider button
    await page.getByRole("button", { name: /Add Provider/i }).click();

    // Wait for dialog to open
    await expect(page.getByText("Add SAML Provider")).toBeVisible();

    // Verify Metadata URL is selected by default
    const metadataUrlButton = page.getByRole("button", { name: /Metadata URL/i });
    await expect(metadataUrlButton).toHaveClass(/bg-blue-100/);

    // Switch to XML upload
    await page.getByRole("button", { name: /Upload XML/i }).click();

    // Verify XML upload option is now active
    const uploadXmlButton = page.getByRole("button", { name: /Upload XML/i });
    await expect(uploadXmlButton).toHaveClass(/bg-blue-100/);

    // Verify file input is visible
    await expect(page.getByText("Choose XML File")).toBeVisible();

    // Switch back to URL
    await metadataUrlButton.click();
    await expect(metadataUrlButton).toHaveClass(/bg-blue-100/);
  });
});
