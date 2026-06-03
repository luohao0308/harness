import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { MenuSelect } from "../menu-select";

function ControlledMenuSelect({ onChange = vi.fn() }: { onChange?: (value: string) => void }) {
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
        { value: "alpha", label: "Alpha", group: "A" },
        { value: "blocked", label: "Blocked", disabled: true, group: "B" },
        { value: "beta", label: "Beta", group: "B" },
      ]}
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
});
