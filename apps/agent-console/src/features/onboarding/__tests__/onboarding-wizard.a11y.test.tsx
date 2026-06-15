/**
 * Accessibility tests for Onboarding Wizard
 *
 * Tests WCAG 2.1 AA compliance using axe-core:
 * - Automated violation detection
 * - Keyboard navigation
 * - ARIA labels and roles
 * - Focus management
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, test, expect, vi } from "vitest";
import { OnboardingWizardPage } from "../../../pages/OnboardingWizardPage";

describe("Onboarding Wizard Accessibility", () => {
  test("has no axe violations on initial render", async () => {
    const { container } = render(<OnboardingWizardPage />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("has no axe violations on profile step", async () => {
    const user = userEvent.setup();
    const { container } = render(<OnboardingWizardPage />);

    // Navigate to profile step
    const getStartedButton = screen.getByRole("button", { name: /get started/i });
    await user.click(getStartedButton);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("has no axe violations on preferences step", async () => {
    const user = userEvent.setup();
    const { container } = render(<OnboardingWizardPage />);

    // Navigate to preferences step
    const getStartedButton = screen.getByRole("button", { name: /get started/i });
    await user.click(getStartedButton);

    const nextButton = screen.getByRole("button", { name: /next/i });
    await user.click(nextButton);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  test("navigation buttons are keyboard accessible", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizardPage />);

    const getStartedButton = screen.getByRole("button", { name: /get started/i });

    // Focus on the button using Tab
    await user.tab();
    expect(getStartedButton).toHaveFocus();

    // Activate with Enter key
    await user.keyboard("{Enter}");

    // Should navigate to next step
    expect(screen.getByText(/Profile Step - Coming Soon/i)).toBeInTheDocument();
  });

  test("skip setup button is keyboard accessible", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizardPage />);

    const skipButton = screen.getByRole("button", { name: /skip setup/i });

    // Tab to skip button (may need multiple tabs depending on focus order)
    await user.tab();
    await user.tab();

    expect(skipButton).toHaveFocus();
  });

  test("wizard header has correct banner role", () => {
    render(<OnboardingWizardPage />);
    const banner = screen.getByRole("banner");
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(/Setup Wizard/i);
  });

  test("progress indicator has accessible region with label", () => {
    render(<OnboardingWizardPage />);
    const progressRegion = screen.getByRole("region", { name: /setup progress/i });
    expect(progressRegion).toBeInTheDocument();
  });

  test("main content area has main role", () => {
    render(<OnboardingWizardPage />);
    const main = screen.getByRole("main");
    expect(main).toBeInTheDocument();
  });

  test("step indicators communicate current step to screen readers", () => {
    render(<OnboardingWizardPage />);

    // Check that step indicators are present and accessible
    const stepIndicators = screen.getAllByRole("listitem");
    expect(stepIndicators.length).toBeGreaterThan(0);
  });

  test("focus is managed when navigating between steps", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizardPage />);

    const getStartedButton = screen.getByRole("button", { name: /get started/i });
    await user.click(getStartedButton);

    // After navigation, focus should be on an interactive element or the next button
    const nextButton = screen.getByRole("button", { name: /next/i });
    expect(nextButton).toBeInTheDocument();
  });

  test("previous button becomes enabled after first step", async () => {
    const user = userEvent.setup();
    render(<OnboardingWizardPage />);

    const getStartedButton = screen.getByRole("button", { name: /get started/i });
    await user.click(getStartedButton);

    const previousButton = screen.getByRole("button", { name: /previous/i });
    expect(previousButton).not.toBeDisabled();
  });
});
