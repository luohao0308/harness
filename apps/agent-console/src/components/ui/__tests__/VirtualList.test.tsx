import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { VirtualList } from "../VirtualList";

describe("VirtualList", () => {
  it("renders accessible list semantics with stable item keys", () => {
    render(
      <VirtualList
        ariaLabel="插件列表"
        items={[
          { id: "github", name: "GitHub" },
          { id: "offline", name: "Offline" },
        ]}
        getItemKey={(item) => item.id}
        renderItem={(item) => <span>{item.name}</span>}
      />,
    );

    const list = screen.getByRole("list", { name: "插件列表" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("GitHub")).toBeInTheDocument();
    expect(within(items[1]).getByText("Offline")).toBeInTheDocument();
  });
});
