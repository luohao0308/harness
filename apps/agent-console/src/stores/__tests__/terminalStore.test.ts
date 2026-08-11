// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

describe("terminal store", () => {
  beforeEach(() => {
    vi.resetModules();
    window.localStorage.clear();
  });

  it("creates stable terminal titles and ignores duplicate creates", async () => {
    const { useTerminalStore } = await import("../terminalStore");
    const store = useTerminalStore.getState();

    store.createTerminal("term-1");
    store.createTerminal("term-2");
    store.createTerminal("term-3");
    store.createTerminal("term-4");
    store.createTerminal("term-1");
    store.createTerminal("term-2");
    store.createTerminal("term-3");
    store.createTerminal("term-4");

    const terminals = useTerminalStore.getState().terminals;
    expect(Object.keys(terminals)).toEqual(["term-1", "term-2", "term-3", "term-4"]);
    expect(Object.values(terminals).map((terminal) => terminal.title)).toEqual([
      "Terminal 1",
      "Terminal 2",
      "Terminal 3",
      "Terminal 4",
    ]);
  });

  it("hydrates legacy horizontal layout with default vertical sizes", async () => {
    window.localStorage.setItem(
      "terminal-layout",
      JSON.stringify({ direction: "horizontal", sizes: [34, 32, 34], collapsed: {} }),
    );

    const { useTerminalStore } = await import("../terminalStore");

    expect(useTerminalStore.getState().layout).toEqual({
      direction: "horizontal",
      sizes: [34, 32, 34],
      verticalSizes: [50, 50],
      collapsed: {},
    });
  });

  it("persists vertical layout sizes", async () => {
    const { useTerminalStore } = await import("../terminalStore");

    useTerminalStore.getState().setLayout({
      direction: "horizontal",
      sizes: [40, 30, 30],
      verticalSizes: [65, 35],
      collapsed: {},
    });

    expect(JSON.parse(window.localStorage.getItem("terminal-layout") || "{}")).toEqual({
      direction: "horizontal",
      sizes: [40, 30, 30],
      verticalSizes: [65, 35],
      collapsed: {},
    });
  });
});
