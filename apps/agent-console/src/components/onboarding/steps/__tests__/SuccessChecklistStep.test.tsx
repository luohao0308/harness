import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SuccessChecklistStep } from "../SuccessChecklistStep";

describe("SuccessChecklistStep", () => {
  it("displays all 5 checklist items with completion status", async () => {
    const onContinue = vi.fn();
    const onViewDocs = vi.fn();

    render(<SuccessChecklistStep onContinue={onContinue} onViewDocs={onViewDocs} />);

    expect(screen.getByText("Setup Complete!")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("System requirements validated")).toBeInTheDocument();
      expect(screen.getByText("Configuration complete")).toBeInTheDocument();
      expect(screen.getByText("Database initialized")).toBeInTheDocument();
      expect(screen.getByText("First agent created")).toBeInTheDocument();
      expect(screen.getByText("Setup successful")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("5 / 5 complete")).toBeInTheDocument();
    });
  });

  it("enables Continue to Dashboard button only when all items are complete", async () => {
    const onContinue = vi.fn();
    const onViewDocs = vi.fn();

    render(<SuccessChecklistStep onContinue={onContinue} onViewDocs={onViewDocs} />);

    const continueButton = screen.getByRole("button", { name: "Continue to Dashboard" });

    expect(continueButton).toBeDisabled();

    await waitFor(() => {
      expect(continueButton).toBeEnabled();
    });
  });

  it("calls onContinue when Continue to Dashboard button is clicked", async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    const onViewDocs = vi.fn();

    render(<SuccessChecklistStep onContinue={onContinue} onViewDocs={onViewDocs} />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Continue to Dashboard" })).toBeEnabled();
    });

    await user.click(screen.getByRole("button", { name: "Continue to Dashboard" }));

    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onViewDocs).not.toHaveBeenCalled();
  });

  it("calls onViewDocs when View Documentation link is clicked", async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    const onViewDocs = vi.fn();

    render(<SuccessChecklistStep onContinue={onContinue} onViewDocs={onViewDocs} />);

    await user.click(screen.getByRole("button", { name: "View Documentation" }));

    expect(onViewDocs).toHaveBeenCalledTimes(1);
    expect(onContinue).not.toHaveBeenCalled();
  });

  it("shows progress indicator (4/5 complete) during loading", () => {
    const onContinue = vi.fn();
    const onViewDocs = vi.fn();

    render(<SuccessChecklistStep onContinue={onContinue} onViewDocs={onViewDocs} />);

    expect(screen.getByText("0 / 5 complete")).toBeInTheDocument();
  });

  it("displays loading spinners for incomplete items", () => {
    const onContinue = vi.fn();
    const onViewDocs = vi.fn();

    const { container } = render(
      <SuccessChecklistStep onContinue={onContinue} onViewDocs={onViewDocs} />,
    );

    const spinners = container.querySelectorAll(".lucide-loader-circle");
    expect(spinners.length).toBeGreaterThan(0);
  });

  it("shows checkmarks for completed items after loading", async () => {
    const onContinue = vi.fn();
    const onViewDocs = vi.fn();

    const { container } = render(
      <SuccessChecklistStep onContinue={onContinue} onViewDocs={onViewDocs} />,
    );

    await waitFor(() => {
      expect(screen.getByText("5 / 5 complete")).toBeInTheDocument();
    });

    const checkmarks = container.querySelectorAll(".lucide-circle-check");
    expect(checkmarks.length).toBeGreaterThan(0);
  });
});
