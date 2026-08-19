import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { DesktopOperationRail } from "../../../components/desktop/DesktopOperationRail";

describe("Desktop automation entry", () => {
  it("links to Agent Studio trigger mode and marks it active", () => {
    render(
      <MemoryRouter initialEntries={["/agents?desktop_panel=triggers"]}>
        <DesktopOperationRail />
      </MemoryRouter>,
    );

    const entry = screen.getByRole("link", { name: "自动化" });
    expect(entry).toHaveAttribute("href", "/agents?desktop_panel=triggers");
    expect(entry).toHaveAttribute("aria-current", "page");
  });
});
