import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { NavigationButtons } from "../NavigationButtons";

describe("NavigationButtons", () => {
  describe("Button Rendering", () => {
    it("renders both next and previous buttons by default", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} />);

      expect(screen.getByRole("button", { name: /go to next step/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /go to previous step/i })).toBeInTheDocument();
    });

    it("renders custom button labels when provided", () => {
      render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
          nextLabel="Continue"
          previousLabel="Go Back"
        />,
      );

      expect(screen.getByText("Continue")).toBeInTheDocument();
      expect(screen.getByText("Go Back")).toBeInTheDocument();
    });

    it("changes next button to Complete on last step", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} isLastStep={true} />);

      expect(screen.getByText("Complete")).toBeInTheDocument();
      expect(screen.queryByText("Next")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /complete setup/i })).toBeInTheDocument();
    });

    it("hides previous button on first step", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} isFirstStep={true} />);

      const previousButton = screen.getByRole("button", { name: /go to previous step/i });
      expect(previousButton).toHaveClass("invisible");
    });
  });

  describe("Button States", () => {
    it("disables next button when canGoNext is false", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} canGoNext={false} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      expect(nextButton).toBeDisabled();
    });

    it("disables previous button when canGoPrevious is false", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} canGoPrevious={false} />);

      const previousButton = screen.getByRole("button", { name: /go to previous step/i });
      expect(previousButton).toBeDisabled();
    });

    it("disables both buttons when isLoading is true", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} isLoading={true} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      const previousButton = screen.getByRole("button", { name: /go to previous step/i });

      expect(nextButton).toBeDisabled();
      expect(previousButton).toBeDisabled();
    });

    it("enables next button by default", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      expect(nextButton).not.toBeDisabled();
    });

    it("enables previous button by default when not first step", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} isFirstStep={false} />);

      const previousButton = screen.getByRole("button", { name: /go to previous step/i });
      expect(previousButton).not.toBeDisabled();
    });
  });

  describe("Click Handlers", () => {
    it("calls onNext when next button is clicked", async () => {
      const user = userEvent.setup();
      const onNext = vi.fn();

      render(<NavigationButtons onNext={onNext} onPrevious={vi.fn()} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      await user.click(nextButton);

      expect(onNext).toHaveBeenCalledTimes(1);
    });

    it("calls onPrevious when previous button is clicked", async () => {
      const user = userEvent.setup();
      const onPrevious = vi.fn();

      render(<NavigationButtons onNext={vi.fn()} onPrevious={onPrevious} />);

      const previousButton = screen.getByRole("button", { name: /go to previous step/i });
      await user.click(previousButton);

      expect(onPrevious).toHaveBeenCalledTimes(1);
    });

    it("does not call onNext when next button is disabled", async () => {
      const user = userEvent.setup();
      const onNext = vi.fn();

      render(<NavigationButtons onNext={onNext} onPrevious={vi.fn()} canGoNext={false} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      await user.click(nextButton);

      expect(onNext).not.toHaveBeenCalled();
    });

    it("does not call onPrevious when previous button is disabled", async () => {
      const user = userEvent.setup();
      const onPrevious = vi.fn();

      render(<NavigationButtons onNext={vi.fn()} onPrevious={onPrevious} canGoPrevious={false} />);

      const previousButton = screen.getByRole("button", { name: /go to previous step/i });
      await user.click(previousButton);

      expect(onPrevious).not.toHaveBeenCalled();
    });
  });

  describe("Accessibility", () => {
    it("has proper ARIA labels for next button", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      expect(nextButton).toHaveAttribute("aria-label", "Go to next step");
    });

    it("has proper ARIA label for complete button on last step", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} isLastStep={true} />);

      const completeButton = screen.getByRole("button", { name: /complete setup/i });
      expect(completeButton).toHaveAttribute("aria-label", "Complete setup");
    });

    it("has proper ARIA labels for previous button", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} />);

      const previousButton = screen.getByRole("button", { name: /go to previous step/i });
      expect(previousButton).toHaveAttribute("aria-label", "Go to previous step");
    });

    it("marks icons as aria-hidden", () => {
      const { container } = render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} />);

      const icons = container.querySelectorAll('svg[aria-hidden="true"]');
      expect(icons.length).toBeGreaterThan(0);
    });
  });

  describe("Button Type", () => {
    it("renders buttons with type=button to prevent form submission", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      const previousButton = screen.getByRole("button", { name: /go to previous step/i });

      expect(nextButton).toHaveAttribute("type", "button");
      expect(previousButton).toHaveAttribute("type", "button");
    });
  });

  describe("Combined States", () => {
    it("handles first step with disabled previous and enabled next", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} isFirstStep={true} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      const previousButton = screen.getByRole("button", { name: /go to previous step/i });

      expect(nextButton).not.toBeDisabled();
      expect(previousButton).toHaveClass("invisible");
    });

    it("handles last step with custom label and both directions enabled", () => {
      render(
        <NavigationButtons
          onNext={vi.fn()}
          onPrevious={vi.fn()}
          isLastStep={true}
          canGoNext={true}
          canGoPrevious={true}
        />,
      );

      const completeButton = screen.getByRole("button", { name: /complete setup/i });
      const previousButton = screen.getByRole("button", { name: /go to previous step/i });

      expect(completeButton).not.toBeDisabled();
      expect(previousButton).not.toBeDisabled();
    });

    it("handles loading state with disabled navigation", () => {
      render(<NavigationButtons onNext={vi.fn()} onPrevious={vi.fn()} isLoading={true} />);

      const nextButton = screen.getByRole("button", { name: /go to next step/i });
      const previousButton = screen.getByRole("button", { name: /go to previous step/i });

      expect(nextButton).toBeDisabled();
      expect(previousButton).toBeDisabled();
      expect(nextButton).toHaveClass("cursor-not-allowed");
    });
  });
});
