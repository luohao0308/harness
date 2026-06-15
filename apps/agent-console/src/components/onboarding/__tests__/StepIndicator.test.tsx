import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { WizardStep } from "../WizardLayout";
import { StepIndicator } from "../StepIndicator";

const mockSteps: WizardStep[] = [
  { id: "step1", title: "Welcome", description: "Get started" },
  { id: "step2", title: "Configuration", description: "Setup your config" },
  { id: "step3", title: "Review", description: "Review settings" },
  { id: "step4", title: "Complete", description: "Finish setup" },
];

describe("StepIndicator", () => {
  describe("Mobile View", () => {
    it("displays step count in mobile view", () => {
      render(<StepIndicator steps={mockSteps} currentStep={0} />);

      expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();
    });

    it("displays current step title in mobile view", () => {
      render(<StepIndicator steps={mockSteps} currentStep={2} />);

      expect(screen.getByText("Step 3 of 4")).toBeInTheDocument();
      expect(screen.getByText("Review")).toBeInTheDocument();
    });

    it("updates step count when currentStep changes", () => {
      const { rerender } = render(<StepIndicator steps={mockSteps} currentStep={0} />);

      expect(screen.getByText("Step 1 of 4")).toBeInTheDocument();

      rerender(<StepIndicator steps={mockSteps} currentStep={3} />);

      expect(screen.getByText("Step 4 of 4")).toBeInTheDocument();
    });
  });

  describe("Desktop View", () => {
    it("renders all steps in desktop view", () => {
      render(<StepIndicator steps={mockSteps} currentStep={0} />);

      mockSteps.forEach((step) => {
        expect(screen.getByText(step.title)).toBeInTheDocument();
      });
    });

    it("displays step descriptions when provided", () => {
      render(<StepIndicator steps={mockSteps} currentStep={0} />);

      mockSteps.forEach((step) => {
        if (step.description) {
          expect(screen.getByText(step.description)).toBeInTheDocument();
        }
      });
    });

    it("renders step numbers for all steps", () => {
      render(<StepIndicator steps={mockSteps} currentStep={0} />);

      // First step should show "1" (current), others show their numbers
      expect(screen.getByText("1")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("3")).toBeInTheDocument();
      expect(screen.getByText("4")).toBeInTheDocument();
    });
  });

  describe("Current Step Highlighting", () => {
    it("marks the current step with aria-current", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={1} />);

      const currentStepCircle = container.querySelector('[aria-current="step"]');
      expect(currentStepCircle).toBeInTheDocument();
    });

    it("applies current step styles", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={1} />);

      const currentStepCircle = container.querySelector('[aria-current="step"]');
      expect(currentStepCircle).toHaveClass("border-blue-600", "bg-white");
    });

    it("highlights current step title with blue color", () => {
      render(<StepIndicator steps={mockSteps} currentStep={1} />);

      const configTitle = screen.getAllByText("Configuration");
      const currentTitle = configTitle.find((el) => el.classList.contains("text-blue-600"));
      expect(currentTitle).toBeInTheDocument();
    });
  });

  describe("Completed Steps Marking", () => {
    it("shows checkmark icon for completed steps", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={2} />);

      // Steps 0 and 1 are completed, should have checkmarks
      const checkIcons = container.querySelectorAll('svg.text-white');
      expect(checkIcons.length).toBeGreaterThanOrEqual(2);
    });

    it("applies completed step styles to circles", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={2} />);

      // First two steps should be completed
      const completedCircles = container.querySelectorAll('.border-blue-600.bg-blue-600');
      expect(completedCircles.length).toBeGreaterThanOrEqual(2);
    });

    it("shows completed connector lines", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={2} />);

      // Lines between completed steps should be blue
      const completedLines = container.querySelectorAll('.bg-blue-600[aria-hidden="true"]');
      expect(completedLines.length).toBeGreaterThan(0);
    });
  });

  describe("Upcoming Steps", () => {
    it("displays step numbers for upcoming steps", () => {
      render(<StepIndicator steps={mockSteps} currentStep={0} />);

      // Steps 2, 3, 4 are upcoming
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("3")).toBeInTheDocument();
      expect(screen.getByText("4")).toBeInTheDocument();
    });

    it("applies upcoming step styles", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={0} />);

      // Upcoming steps should have grey borders
      const upcomingCircles = container.querySelectorAll('.border-slate-300.bg-white');
      expect(upcomingCircles.length).toBeGreaterThan(0);
    });

    it("shows grey text for upcoming step titles", () => {
      render(<StepIndicator steps={mockSteps} currentStep={0} />);

      const reviewTitle = screen.getAllByText("Review");
      const upcomingTitle = reviewTitle.find((el) => el.classList.contains("text-slate-500"));
      expect(upcomingTitle).toBeInTheDocument();
    });
  });

  describe("Step Progression", () => {
    it("correctly shows all completed when on last step", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={3} />);

      // All previous steps should be completed (3 completed circles)
      const completedCircles = container.querySelectorAll('.border-blue-600.bg-blue-600');
      expect(completedCircles.length).toBe(3);
    });

    it("shows no completed steps on first step", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={0} />);

      // No completed circles, only current and upcoming
      const completedCircles = container.querySelectorAll('.border-blue-600.bg-blue-600');
      expect(completedCircles.length).toBe(0);
    });

    it("correctly calculates step states for middle step", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={2} />);

      // 2 completed, 1 current, 1 upcoming
      const completedCircles = container.querySelectorAll('.border-blue-600.bg-blue-600');
      const currentCircle = container.querySelector('[aria-current="step"]');
      const upcomingCircles = container.querySelectorAll('.border-slate-300.bg-white');

      expect(completedCircles.length).toBe(2);
      expect(currentCircle).toBeInTheDocument();
      expect(upcomingCircles.length).toBeGreaterThan(0);
    });
  });

  describe("Connector Lines", () => {
    it("renders connector lines between steps", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={0} />);

      // Should have 3 connector lines for 4 steps
      const connectorLines = container.querySelectorAll('[aria-hidden="true"].h-0\\.5');
      expect(connectorLines.length).toBe(3);
    });

    it("does not render connector after last step", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={0} />);

      // Count all list items (steps) and connectors
      const stepItems = container.querySelectorAll('li');
      const connectors = container.querySelectorAll('[aria-hidden="true"].h-0\\.5');

      expect(connectors.length).toBe(stepItems.length - 1);
    });

    it("colors completed connectors blue", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={2} />);

      // At least one connector should be blue (completed)
      const blueConnectors = container.querySelectorAll('.bg-blue-600[aria-hidden="true"]');
      expect(blueConnectors.length).toBeGreaterThan(0);
    });

    it("colors upcoming connectors grey", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={0} />);

      // All connectors should be grey (none completed)
      const greyConnectors = container.querySelectorAll('.bg-slate-300[aria-hidden="true"]');
      expect(greyConnectors.length).toBeGreaterThan(0);
    });
  });

  describe("Accessibility", () => {
    it("has proper navigation landmark", () => {
      render(<StepIndicator steps={mockSteps} currentStep={0} />);

      const nav = screen.getByRole("navigation", { name: /progress/i });
      expect(nav).toBeInTheDocument();
    });

    it("uses ordered list for step structure", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={0} />);

      const orderedList = container.querySelector("ol");
      expect(orderedList).toBeInTheDocument();
    });

    it("marks decorative icons as aria-hidden", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={2} />);

      const hiddenIcons = container.querySelectorAll('svg[aria-hidden="true"]');
      expect(hiddenIcons.length).toBeGreaterThan(0);
    });

    it("includes aria-current for current step", () => {
      const { container } = render(<StepIndicator steps={mockSteps} currentStep={1} />);

      const currentStep = container.querySelector('[aria-current="step"]');
      expect(currentStep).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("handles single step", () => {
      const singleStep: WizardStep[] = [{ id: "only", title: "Only Step" }];
      render(<StepIndicator steps={singleStep} currentStep={0} />);

      expect(screen.getByText("Step 1 of 1")).toBeInTheDocument();
      expect(screen.getByText("Only Step")).toBeInTheDocument();
    });

    it("handles many steps", () => {
      const manySteps: WizardStep[] = Array.from({ length: 10 }, (_, i) => ({
        id: `step${i + 1}`,
        title: `Step ${i + 1}`,
      }));

      render(<StepIndicator steps={manySteps} currentStep={5} />);

      expect(screen.getByText("Step 6 of 10")).toBeInTheDocument();
    });

    it("handles steps without descriptions", () => {
      const stepsNoDesc: WizardStep[] = [
        { id: "s1", title: "First" },
        { id: "s2", title: "Second" },
      ];

      render(<StepIndicator steps={stepsNoDesc} currentStep={0} />);

      expect(screen.getByText("First")).toBeInTheDocument();
      expect(screen.getByText("Second")).toBeInTheDocument();
    });
  });
});
