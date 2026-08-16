import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { WizardStep } from "../WizardLayout";
import { WizardLayout } from "../WizardLayout";

const mockSteps: WizardStep[] = [
  { id: "step1", title: "Welcome", description: "Get started" },
  { id: "step2", title: "Profile", description: "Setup your profile" },
  { id: "step3", title: "Preferences", description: "Choose your preferences" },
  { id: "step4", title: "Team", description: "Invite team members" },
  { id: "step5", title: "Integrations", description: "Connect services" },
  { id: "step6", title: "Review", description: "Review your settings" },
  { id: "step7", title: "Complete", description: "Finish setup" },
];

describe("WizardLayout", () => {
  it("renders all 7 steps with progress indicator", () => {
    render(
      <WizardLayout steps={mockSteps} currentStep={0} onNext={vi.fn()} onPrevious={vi.fn()}>
        <div>Step content</div>
      </WizardLayout>,
    );

    expect(screen.getByText("Setup Wizard")).toBeInTheDocument();
    expect(screen.getByText("Step content")).toBeInTheDocument();

    // Mobile view shows current step count
    expect(screen.getByText("Step 1 of 7")).toBeInTheDocument();
  });

  it("shows current step in progress indicator", () => {
    render(
      <WizardLayout steps={mockSteps} currentStep={2} onNext={vi.fn()} onPrevious={vi.fn()}>
        <div>Step 3 content</div>
      </WizardLayout>,
    );

    // Mobile view
    expect(screen.getByText("Step 3 of 7")).toBeInTheDocument();
    expect(screen.getAllByText("Preferences").length).toBeGreaterThan(0);
  });

  it("handles next button click", async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();

    render(
      <WizardLayout steps={mockSteps} currentStep={0} onNext={onNext} onPrevious={vi.fn()}>
        <div>Content</div>
      </WizardLayout>,
    );

    const nextButton = screen.getByRole("button", { name: "Next" });
    await user.click(nextButton);

    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("handles previous button click", async () => {
    const user = userEvent.setup();
    const onPrevious = vi.fn();

    render(
      <WizardLayout steps={mockSteps} currentStep={2} onNext={vi.fn()} onPrevious={onPrevious}>
        <div>Content</div>
      </WizardLayout>,
    );

    const previousButton = screen.getByRole("button", { name: "Previous" });
    await user.click(previousButton);

    expect(onPrevious).toHaveBeenCalledTimes(1);
  });

  it("displays skip setup link when onSkip is provided", async () => {
    const user = userEvent.setup();
    const onSkip = vi.fn();

    render(
      <WizardLayout
        steps={mockSteps}
        currentStep={0}
        onNext={vi.fn()}
        onPrevious={vi.fn()}
        onSkip={onSkip}
      >
        <div>Content</div>
      </WizardLayout>,
    );

    const skipLink = screen.getByRole("button", { name: "Skip Setup" });
    expect(skipLink).toBeInTheDocument();

    await user.click(skipLink);
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it("hides previous button on first step", () => {
    render(
      <WizardLayout steps={mockSteps} currentStep={0} onNext={vi.fn()} onPrevious={vi.fn()}>
        <div>Content</div>
      </WizardLayout>,
    );

    const previousButton = screen.getByRole("button", { name: "Previous" });
    expect(previousButton).toHaveClass("invisible");
  });

  it("shows complete button on last step", () => {
    render(
      <WizardLayout steps={mockSteps} currentStep={6} onNext={vi.fn()} onPrevious={vi.fn()}>
        <div>Content</div>
      </WizardLayout>,
    );

    expect(screen.getByRole("button", { name: "Complete" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
  });

  it("disables next button when canGoNext is false", () => {
    render(
      <WizardLayout
        steps={mockSteps}
        currentStep={0}
        onNext={vi.fn()}
        onPrevious={vi.fn()}
        canGoNext={false}
      >
        <div>Content</div>
      </WizardLayout>,
    );

    const nextButton = screen.getByRole("button", { name: "Next" });
    expect(nextButton).toBeDisabled();
  });

  it("disables previous button when canGoPrevious is false", () => {
    render(
      <WizardLayout
        steps={mockSteps}
        currentStep={2}
        onNext={vi.fn()}
        onPrevious={vi.fn()}
        canGoPrevious={false}
      >
        <div>Content</div>
      </WizardLayout>,
    );

    const previousButton = screen.getByRole("button", { name: "Previous" });
    expect(previousButton).toBeDisabled();
  });

  it("supports custom button labels", () => {
    render(
      <WizardLayout
        steps={mockSteps}
        currentStep={1}
        onNext={vi.fn()}
        onPrevious={vi.fn()}
        nextLabel="Continue"
        previousLabel="Go Back"
        skipLabel="Skip All"
        onSkip={vi.fn()}
      >
        <div>Content</div>
      </WizardLayout>,
    );

    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go Back" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Skip All" })).toBeInTheDocument();
  });

  it("renders children content correctly", () => {
    render(
      <WizardLayout steps={mockSteps} currentStep={0} onNext={vi.fn()} onPrevious={vi.fn()}>
        <div data-testid="wizard-content">
          <h2>Custom Content</h2>
          <p>This is step-specific content</p>
        </div>
      </WizardLayout>,
    );

    expect(screen.getByTestId("wizard-content")).toBeInTheDocument();
    expect(screen.getByText("Custom Content")).toBeInTheDocument();
    expect(screen.getByText("This is step-specific content")).toBeInTheDocument();
  });
});
