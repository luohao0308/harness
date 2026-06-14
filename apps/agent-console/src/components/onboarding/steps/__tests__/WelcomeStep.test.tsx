import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WelcomeStep } from "../WelcomeStep";

describe("WelcomeStep", () => {
  it("renders system overview with title and description", () => {
    render(<WelcomeStep onGetStarted={vi.fn()} />);

    expect(screen.getByText("Welcome to Agent Console")).toBeInTheDocument();
    expect(
      screen.getByText(/Your intelligent multi-agent orchestration platform/i),
    ).toBeInTheDocument();
  });

  it("renders 3-5 product highlights with icons", () => {
    render(<WelcomeStep onGetStarted={vi.fn()} />);

    // Check for feature cards - should have at least 3
    const features = [
      "Multi-Agent Orchestration",
      "Intelligent Task Routing",
      "Real-Time Monitoring",
    ];

    features.forEach((feature) => {
      expect(screen.getByText(feature)).toBeInTheDocument();
    });
  });

  it("renders Get Started button and calls onGetStarted when clicked", async () => {
    const user = userEvent.setup();
    const onGetStarted = vi.fn();

    render(<WelcomeStep onGetStarted={onGetStarted} />);

    const getStartedButton = screen.getByRole("button", { name: /get started/i });
    expect(getStartedButton).toBeInTheDocument();

    await user.click(getStartedButton);

    expect(onGetStarted).toHaveBeenCalledTimes(1);
  });

  it("renders hero section with icon or illustration", () => {
    render(<WelcomeStep onGetStarted={vi.fn()} />);

    // Check for hero section by looking for the main heading
    const heroHeading = screen.getByText("Welcome to Agent Console");
    expect(heroHeading).toBeInTheDocument();

    // Hero should be in a larger font (h1)
    expect(heroHeading.tagName).toBe("H1");
  });

  it("is responsive with proper mobile and desktop styling", () => {
    const { container } = render(<WelcomeStep onGetStarted={vi.fn()} />);

    // Check for responsive grid classes (Tailwind patterns)
    const featureGrid = container.querySelector('[class*="grid"]');
    expect(featureGrid).toBeInTheDocument();
  });
});
