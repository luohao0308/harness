import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SSOLoginButton } from "../SSOLoginButton";
import { ProviderSelector } from "../ProviderSelector";
import type { SamlProvider } from "../SSOLoginButton";

describe("SSOLoginButton", () => {
  const mockProviders: SamlProvider[] = [
    { id: "okta-1", name: "Okta", enabled: true },
    { id: "azure-1", name: "Azure AD", enabled: true },
  ];

  it("renders SSO button when providers are available", () => {
    const mockInitiateSSO = vi.fn();
    render(<SSOLoginButton providers={mockProviders} onInitiateSSO={mockInitiateSSO} />);

    expect(screen.getByRole("button", { name: /使用 SSO 登录/i })).toBeInTheDocument();
  });

  it("does not render when no enabled providers exist", () => {
    const mockInitiateSSO = vi.fn();
    const disabledProviders: SamlProvider[] = [{ id: "okta-1", name: "Okta", enabled: false }];

    const { container } = render(<SSOLoginButton providers={disabledProviders} onInitiateSSO={mockInitiateSSO} />);

    expect(container.firstChild).toBeNull();
  });

  it("initiates SSO directly when only one provider is available", async () => {
    const user = userEvent.setup();
    const mockInitiateSSO = vi.fn(async () => {});
    const singleProvider: SamlProvider[] = [{ id: "okta-1", name: "Okta", enabled: true }];

    render(<SSOLoginButton providers={singleProvider} onInitiateSSO={mockInitiateSSO} />);

    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    await waitFor(() => {
      expect(mockInitiateSSO).toHaveBeenCalledWith("okta-1");
      expect(mockInitiateSSO).toHaveBeenCalledTimes(1);
    });
  });

  it("shows provider selector when multiple providers are available", async () => {
    const user = userEvent.setup();
    const mockInitiateSSO = vi.fn(async () => {});

    render(<SSOLoginButton providers={mockProviders} onInitiateSSO={mockInitiateSSO} />);

    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    expect(screen.getByText("选择 SSO 提供商")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Okta/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Azure AD/i })).toBeInTheDocument();
  });

  it("initiates SSO with selected provider from selector", async () => {
    const user = userEvent.setup();
    const mockInitiateSSO = vi.fn(async () => {});

    render(<SSOLoginButton providers={mockProviders} onInitiateSSO={mockInitiateSSO} />);

    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    const azureButton = screen.getByRole("button", { name: /Azure AD/i });
    await user.click(azureButton);

    await waitFor(() => {
      expect(mockInitiateSSO).toHaveBeenCalledWith("azure-1");
      expect(mockInitiateSSO).toHaveBeenCalledTimes(1);
    });
  });

  it("shows loading state during SSO initiation", async () => {
    const user = userEvent.setup();
    let resolvePromise: () => void;
    const mockInitiateSSO = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolvePromise = resolve;
        }),
    );
    const singleProvider: SamlProvider[] = [{ id: "okta-1", name: "Okta", enabled: true }];

    render(<SSOLoginButton providers={singleProvider} onInitiateSSO={mockInitiateSSO} />);

    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    const spinner = await screen.findByRole("button");
    expect(spinner).toBeDisabled();

    resolvePromise!();
  });

  it("displays error message when SSO initiation fails", async () => {
    const user = userEvent.setup();
    const mockInitiateSSO = vi.fn(async () => {
      throw new Error("IdP 连接失败");
    });
    const singleProvider: SamlProvider[] = [{ id: "okta-1", name: "Okta", enabled: true }];

    render(<SSOLoginButton providers={singleProvider} onInitiateSSO={mockInitiateSSO} />);

    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    await waitFor(() => {
      expect(screen.getByText("IdP 连接失败")).toBeInTheDocument();
    });
  });

  it("allows canceling provider selection", async () => {
    const user = userEvent.setup();
    const mockInitiateSSO = vi.fn(async () => {});

    render(<SSOLoginButton providers={mockProviders} onInitiateSSO={mockInitiateSSO} />);

    const ssoButton = screen.getByRole("button", { name: /使用 SSO 登录/i });
    await user.click(ssoButton);

    expect(screen.getByText("选择 SSO 提供商")).toBeInTheDocument();

    const cancelButton = screen.getByRole("button", { name: /取消/i });
    await user.click(cancelButton);

    expect(screen.queryByText("选择 SSO 提供商")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /使用 SSO 登录/i })).toBeInTheDocument();
    expect(mockInitiateSSO).not.toHaveBeenCalled();
  });
});

describe("ProviderSelector", () => {
  const mockProviders: SamlProvider[] = [
    { id: "okta-1", name: "Okta", enabled: true },
    { id: "azure-1", name: "Azure AD", enabled: true },
  ];

  it("renders all providers", () => {
    const mockOnSelect = vi.fn();
    const mockOnCancel = vi.fn();

    render(<ProviderSelector providers={mockProviders} onSelect={mockOnSelect} onCancel={mockOnCancel} />);

    expect(screen.getByText("选择 SSO 提供商")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Okta/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Azure AD/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /取消/i })).toBeInTheDocument();
  });

  it("calls onSelect when a provider is clicked", async () => {
    const user = userEvent.setup();
    const mockOnSelect = vi.fn();
    const mockOnCancel = vi.fn();

    render(<ProviderSelector providers={mockProviders} onSelect={mockOnSelect} onCancel={mockOnCancel} />);

    const oktaButton = screen.getByRole("button", { name: /Okta/i });
    await user.click(oktaButton);

    expect(mockOnSelect).toHaveBeenCalledWith("okta-1");
    expect(mockOnSelect).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when cancel button is clicked", async () => {
    const user = userEvent.setup();
    const mockOnSelect = vi.fn();
    const mockOnCancel = vi.fn();

    render(<ProviderSelector providers={mockProviders} onSelect={mockOnSelect} onCancel={mockOnCancel} />);

    const cancelButton = screen.getByRole("button", { name: /取消/i });
    await user.click(cancelButton);

    expect(mockOnCancel).toHaveBeenCalledTimes(1);
    expect(mockOnSelect).not.toHaveBeenCalled();
  });
});
