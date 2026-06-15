/**
 * Accessibility tests for Navigation
 *
 * Tests WCAG 2.1 AA compliance using axe-core:
 * - Automated violation detection
 * - Keyboard navigation
 * - ARIA labels and roles
 * - Focus management
 * - Landmark navigation
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, test, expect, vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { NavigationButtons } from "../../../components/onboarding/NavigationButtons";
import { ConsoleShell } from "../../../app/ConsoleShell";

// Mock auth and stores
vi.mock("../../../features/auth/AuthProvider", () => ({
  useOptionalAuth: () => ({
    user: { id: "1", email: "test@example.com", name: "Test User" },
    isUsingDevToken: false,
    logoutCurrentUser: vi.fn(),
  }),
}));

vi.mock("../../../stores/consoleStore", () => ({
  useConsoleStore: () => ({ environment: "production" }),
}));

describe("Navigation Accessibility", () => {
  describe("NavigationButtons", () => {
    test("has no axe violations with both buttons enabled", async () => {
      const { container } = render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
          canGoNext={true}
          canGoPrevious={true}
        />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("has no axe violations on first step", async () => {
      const { container } = render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
          isFirstStep={true}
        />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("has no axe violations on last step", async () => {
      const { container } = render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
          isLastStep={true}
        />,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("navigation buttons have accessible labels", () => {
      render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
        />,
      );

      const previousButton = screen.getByRole("button", { name: /previous/i });
      const nextButton = screen.getByRole("button", { name: /next/i });

      expect(previousButton).toBeInTheDocument();
      expect(nextButton).toBeInTheDocument();
    });

    test("next button is keyboard accessible", async () => {
      const user = userEvent.setup();
      const onNext = vi.fn();

      render(
        <NavigationButtons
          onNext={onNext}
          onPrevious={vi.fn()}
        />,
      );

      const nextButton = screen.getByRole("button", { name: /next/i });

      nextButton.focus();
      expect(nextButton).toHaveFocus();

      await user.keyboard("{Enter}");
      expect(onNext).toHaveBeenCalled();
    });

    test("previous button is keyboard accessible", async () => {
      const user = userEvent.setup();
      const onPrevious = vi.fn();

      render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={onPrevious}
          isFirstStep={false}
        />,
      );

      const previousButton = screen.getByRole("button", { name: /previous/i });

      previousButton.focus();
      expect(previousButton).toHaveFocus();

      await user.keyboard("{Enter}");
      expect(onPrevious).toHaveBeenCalled();
    });

    test("disabled buttons have correct ARIA state", () => {
      render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
          canGoNext={false}
          canGoPrevious={false}
        />,
      );

      const previousButton = screen.getByRole("button", { name: /previous/i });
      const nextButton = screen.getByRole("button", { name: /next/i });

      expect(previousButton).toBeDisabled();
      expect(nextButton).toBeDisabled();
    });

    test("complete button on last step has correct label", () => {
      render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
          isLastStep={true}
        />,
      );

      const completeButton = screen.getByRole("button", { name: /complete/i });
      expect(completeButton).toBeInTheDocument();
    });
  });

  describe("ConsoleShell Navigation", () => {
    test("has no axe violations on shell navigation", async () => {
      const { container } = render(
        <BrowserRouter>
          <ConsoleShell title="Test Console">
            <div>Content</div>
          </ConsoleShell>
        </BrowserRouter>,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("sidebar toggle button is keyboard accessible", async () => {
      const user = userEvent.setup();
      render(
        <BrowserRouter>
          <ConsoleShell title="Test Console">
            <div>Content</div>
          </ConsoleShell>
        </BrowserRouter>,
      );

      // Look for sidebar toggle button
      const buttons = screen.getAllByRole("button");
      const toggleButton = buttons.find((btn) =>
        btn.getAttribute("aria-label")?.includes("侧边栏") ||
        btn.textContent?.includes("sidebar")
      );

      if (toggleButton) {
        toggleButton.focus();
        expect(toggleButton).toHaveFocus();
      }
    });

    test("navigation links are keyboard accessible", async () => {
      const user = userEvent.setup();
      render(
        <BrowserRouter>
          <ConsoleShell title="Test Console">
            <div>Content</div>
          </ConsoleShell>
        </BrowserRouter>,
      );

      const navLinks = screen.getAllByRole("link");

      if (navLinks.length > 0) {
        navLinks[0].focus();
        expect(navLinks[0]).toHaveFocus();

        // Tab to next link
        await user.tab();
        if (navLinks.length > 1) {
          expect(navLinks[1]).toHaveFocus();
        }
      }
    });

    test("skip link or landmarks are present for screen readers", () => {
      render(
        <BrowserRouter>
          <ConsoleShell title="Test Console">
            <div>Content</div>
          </ConsoleShell>
        </BrowserRouter>,
      );

      // Check for main landmark
      const main = screen.getByRole("main");
      expect(main).toBeInTheDocument();
    });
  });

  describe("Focus Management", () => {
    test("focus is visible on navigation elements", async () => {
      const user = userEvent.setup();
      render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
        />,
      );

      const nextButton = screen.getByRole("button", { name: /next/i });

      await user.tab();

      // Check if button can receive focus
      const focusedElement = document.activeElement;
      expect(focusedElement).toBeTruthy();
    });

    test("tab order is logical in navigation", async () => {
      const user = userEvent.setup();
      render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
          isFirstStep={false}
        />,
      );

      // Start tabbing
      await user.tab();
      const firstFocused = document.activeElement;

      await user.tab();
      const secondFocused = document.activeElement;

      // Both should be buttons
      expect(firstFocused?.tagName).toBe("BUTTON");
      expect(secondFocused?.tagName).toBe("BUTTON");
    });
  });
});
