import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../../lib/desktop-bridge", () => ({ isDesktopRuntime: vi.fn() }));
vi.mock("../AdvancedFeaturesPage", () => ({ AdvancedFeaturesPage: () => <div>browser advanced page</div> }));
vi.mock("../DesktopSettingsPage", () => ({ DesktopSettingsPage: () => <div>desktop settings center</div> }));

import { isDesktopRuntime } from "../../../../lib/desktop-bridge";
import { DesktopSettingsRoutePage } from "../DesktopSettingsRoutePage";

describe("DesktopSettingsRoutePage", () => {
  beforeEach(() => vi.mocked(isDesktopRuntime).mockReset());

  it("uses the desktop settings center only inside Electron", () => {
    vi.mocked(isDesktopRuntime).mockReturnValue(true);
    render(<DesktopSettingsRoutePage />);
    expect(screen.getByText("desktop settings center")).toBeInTheDocument();
  });

  it("preserves the existing browser advanced surface", () => {
    vi.mocked(isDesktopRuntime).mockReturnValue(false);
    render(<DesktopSettingsRoutePage />);
    expect(screen.getByText("browser advanced page")).toBeInTheDocument();
  });
});
