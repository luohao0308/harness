import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { MenuSelect } from "../menu-select";

function ControlledMenuSelect({
  onChange = vi.fn(),
  showSelectedDescription,
}: {
  onChange?: (value: string) => void;
  showSelectedDescription?: boolean;
}) {
  const [value, setValue] = useState("alpha");

  return (
    <MenuSelect
      ariaLabel="选择项目"
      value={value}
      onChange={(nextValue) => {
        setValue(nextValue);
        onChange(nextValue);
      }}
      options={[
        { value: "alpha", label: "Alpha", description: "Alpha detail", group: "A" },
        { value: "blocked", label: "Blocked", disabled: true, group: "B" },
        { value: "beta", label: "Beta", description: "Beta detail", group: "B" },
      ]}
      showSelectedDescription={showSelectedDescription}
    />
  );
}

describe("MenuSelect", () => {
  it("supports keyboard selection while skipping disabled options", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ControlledMenuSelect onChange={onChange} />);

    const trigger = screen.getByRole("button", { name: "选择项目：Alpha" });
    await user.click(trigger);

    const listbox = screen.getByRole("listbox", { name: "选择项目" });
    await waitFor(() => expect(listbox).toHaveFocus());

    await user.keyboard("{ArrowDown}{Enter}");

    expect(onChange).toHaveBeenCalledWith("beta");
    expect(screen.getByRole("button", { name: "选择项目：Beta" })).toHaveFocus();
    expect(screen.queryByRole("listbox", { name: "选择项目" })).not.toBeInTheDocument();
  });

  it("can keep the selected trigger to one line while preserving option descriptions", async () => {
    const user = userEvent.setup();
    render(<ControlledMenuSelect showSelectedDescription={false} />);

    const trigger = screen.getByRole("button", { name: "选择项目：Alpha" });
    expect(within(trigger).queryByText("Alpha detail")).not.toBeInTheDocument();

    await user.click(trigger);

    const listbox = screen.getByRole("listbox", { name: "选择项目" });
    expect(within(listbox).getByText("Alpha detail")).toBeInTheDocument();
    expect(within(listbox).getByText("Beta detail")).toBeInTheDocument();
  });
});
