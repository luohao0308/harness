// @vitest-environment jsdom
import { waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { installDesktopBridge } from "../desktop-bridge";

describe("installDesktopBridge", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete window.desktopApi;
  });

  test("does nothing outside the Electron desktop shell", () => {
    const navigate = vi.fn();
    const dispose = installDesktopBridge({ navigate });

    dispose();

    expect(navigate).not.toHaveBeenCalled();
  });

  test("navigates to a pending desktop route on startup", async () => {
    const navigate = vi.fn();
    const pendingRoute: DesktopRoutePayload = {
      route: "/runs/run-1?focus=events",
      source: "deep-link",
    };
    window.desktopApi = {
      system: {
        getPendingRoute: vi.fn(async () => pendingRoute),
      },
    };

    installDesktopBridge({ navigate });
    await waitFor(() => {
      expect(navigate).toHaveBeenCalledWith("/runs/run-1?focus=events");
    });
  });

  test("subscribes to native open-route events and unsubscribes cleanly", () => {
    const navigate = vi.fn();
    const unsubscribe = vi.fn();
    let openRoute: (payload: DesktopRoutePayload) => void = () => undefined;

    window.desktopApi = {
      events: {
        onOpenRoute: vi.fn((callback) => {
          openRoute = callback;
          return unsubscribe;
        }),
      },
    };

    const dispose = installDesktopBridge({ navigate });

    openRoute({
      route: "https://agentharness.local/teams/team-1#board",
      source: "notification",
    });

    expect(navigate).toHaveBeenCalledWith("/teams/team-1#board");

    dispose();
    expect(unsubscribe).toHaveBeenCalled();
  });
});
