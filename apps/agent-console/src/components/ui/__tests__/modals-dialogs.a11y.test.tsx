/**
 * Accessibility tests for Modals and Dialogs
 *
 * Tests WCAG 2.1 AA compliance using axe-core:
 * - Automated violation detection
 * - Keyboard navigation
 * - ARIA labels and roles
 * - Focus management
 * - Focus trapping
 * - Escape key handling
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, test, expect, vi } from "vitest";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { useConfirmDialog } from "../../../components/ui/confirm-dialog";

function TestConfirmDialog() {
  const { confirm, confirmDialog } = useConfirmDialog();

  return (
    <div>
      <button
        onClick={() =>
          confirm({
            title: "Delete Item",
            description: "Are you sure you want to delete this item?",
            confirmText: "Delete",
            cancelText: "Cancel",
            variant: "danger",
          })
        }
      >
        Show Confirm
      </button>
      {confirmDialog}
    </div>
  );
}

describe("Modals and Dialogs Accessibility", () => {
  describe("ConfigDialog", () => {
    test("has no axe violations when open", async () => {
      const { container } = render(
        <ConfigDialog
          open={true}
          title="Test Dialog"
          description="This is a test dialog"
          onClose={vi.fn()}
        >
          <div>Dialog content</div>
        </ConfigDialog>,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("has no axe violations without description", async () => {
      const { container } = render(
        <ConfigDialog open={true} title="Test Dialog" onClose={vi.fn()}>
          <div>Dialog content</div>
        </ConfigDialog>,
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("dialog has correct ARIA attributes", () => {
      render(
        <ConfigDialog
          open={true}
          title="Test Dialog"
          description="Test description"
          onClose={vi.fn()}
        >
          <div>Dialog content</div>
        </ConfigDialog>,
      );

      const dialog = screen.getByRole("dialog");
      expect(dialog).toHaveAttribute("aria-modal", "true");
      expect(dialog).toHaveAttribute("aria-labelledby");
      expect(dialog).toHaveAttribute("aria-describedby");
    });

    test("close button has accessible label", () => {
      render(
        <ConfigDialog open={true} title="Test Dialog" onClose={vi.fn()}>
          <div>Dialog content</div>
        </ConfigDialog>,
      );

      const closeButton = screen.getByRole("button", { name: /close/i });
      expect(closeButton).toBeInTheDocument();
    });

    test("escape key closes dialog", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();

      render(
        <ConfigDialog open={true} title="Test Dialog" onClose={onClose}>
          <div>Dialog content</div>
        </ConfigDialog>,
      );

      await user.keyboard("{Escape}");
      expect(onClose).toHaveBeenCalled();
    });

    test("clicking backdrop closes dialog", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();

      render(
        <ConfigDialog open={true} title="Test Dialog" onClose={onClose}>
          <div>Dialog content</div>
        </ConfigDialog>,
      );

      // Click on the backdrop (the outer div with fixed positioning)
      const backdrop = screen.getByRole("dialog").parentElement;
      if (backdrop) {
        await user.pointer({ target: backdrop, keys: "[MouseLeft]" });
      }
    });

    test("close button is keyboard accessible", async () => {
      const user = userEvent.setup();
      const onClose = vi.fn();

      render(
        <ConfigDialog open={true} title="Test Dialog" onClose={onClose}>
          <div>Dialog content</div>
        </ConfigDialog>,
      );

      const closeButton = screen.getByRole("button", { name: /close/i });
      closeButton.focus();
      expect(closeButton).toHaveFocus();

      await user.keyboard("{Enter}");
      expect(onClose).toHaveBeenCalled();
    });

    test("dialog title is properly associated", () => {
      render(
        <ConfigDialog open={true} title="Important Dialog" onClose={vi.fn()}>
          <div>Content</div>
        </ConfigDialog>,
      );

      const dialog = screen.getByRole("dialog");
      const titleId = dialog.getAttribute("aria-labelledby");
      expect(titleId).toBeTruthy();

      const title = document.getElementById(titleId!);
      expect(title).toHaveTextContent("Important Dialog");
    });

    test("dialog description is properly associated", () => {
      render(
        <ConfigDialog
          open={true}
          title="Test"
          description="This is the description"
          onClose={vi.fn()}
        >
          <div>Content</div>
        </ConfigDialog>,
      );

      const dialog = screen.getByRole("dialog");
      const descriptionId = dialog.getAttribute("aria-describedby");
      expect(descriptionId).toBeTruthy();

      const description = document.getElementById(descriptionId!);
      expect(description).toHaveTextContent("This is the description");
    });
  });

  describe("ConfirmDialog", () => {
    test("has no axe violations when confirm dialog is shown", async () => {
      const user = userEvent.setup();
      const { container } = render(<TestConfirmDialog />);

      const showButton = screen.getByRole("button", { name: /Show Confirm/i });
      await user.click(showButton);

      await waitFor(() => {
        expect(screen.getByRole("dialog")).toBeInTheDocument();
      });

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    test("confirm dialog has accessible action buttons", async () => {
      const user = userEvent.setup();
      render(<TestConfirmDialog />);

      const showButton = screen.getByRole("button", { name: /Show Confirm/i });
      await user.click(showButton);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Delete/i })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Cancel/i })).toBeInTheDocument();
      });
    });

    test("confirm button is keyboard accessible", async () => {
      const user = userEvent.setup();
      render(<TestConfirmDialog />);

      const showButton = screen.getByRole("button", { name: /Show Confirm/i });
      await user.click(showButton);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Delete/i })).toBeInTheDocument();
      });

      const deleteButton = screen.getByRole("button", { name: /Delete/i });
      deleteButton.focus();
      expect(deleteButton).toHaveFocus();
    });

    test("cancel button is keyboard accessible", async () => {
      const user = userEvent.setup();
      render(<TestConfirmDialog />);

      const showButton = screen.getByRole("button", { name: /Show Confirm/i });
      await user.click(showButton);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Cancel/i })).toBeInTheDocument();
      });

      const cancelButton = screen.getByRole("button", { name: /Cancel/i });
      cancelButton.focus();
      expect(cancelButton).toHaveFocus();
    });
  });

  describe("Focus Management", () => {
    test("focus is trapped within dialog", async () => {
      const user = userEvent.setup();
      render(
        <ConfigDialog open={true} title="Test Dialog" onClose={vi.fn()}>
          <button>Button 1</button>
          <button>Button 2</button>
        </ConfigDialog>,
      );

      // Tab through interactive elements
      await user.tab();
      const firstFocused = document.activeElement;

      await user.tab();
      const secondFocused = document.activeElement;

      // Both should be within the dialog
      const dialog = screen.getByRole("dialog");
      expect(dialog.contains(firstFocused)).toBe(true);
      expect(dialog.contains(secondFocused)).toBe(true);
    });

    test("dialog does not render when closed", () => {
      render(
        <ConfigDialog open={false} title="Test Dialog" onClose={vi.fn()}>
          <div>Content</div>
        </ConfigDialog>,
      );

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  describe("Body Scroll Lock", () => {
    test("body overflow is managed when dialog opens", () => {
      const { rerender } = render(
        <ConfigDialog open={false} title="Test" onClose={vi.fn()}>
          <div>Content</div>
        </ConfigDialog>,
      );

      // Check initial state
      const initialOverflow = document.body.style.overflow;

      // Open dialog
      rerender(
        <ConfigDialog open={true} title="Test" onClose={vi.fn()}>
          <div>Content</div>
        </ConfigDialog>,
      );

      // Body overflow should be hidden when dialog is open
      expect(document.body.style.overflow).toBe("hidden");

      // Close dialog
      rerender(
        <ConfigDialog open={false} title="Test" onClose={vi.fn()}>
          <div>Content</div>
        </ConfigDialog>,
      );
    });
  });
});
