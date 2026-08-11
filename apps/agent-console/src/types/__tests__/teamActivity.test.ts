import { describe, expect, it } from "vitest";
import { isTeamActivity, type TeamActivity } from "../teamActivity";

describe("teamActivity", () => {
  describe("isTeamActivity", () => {
    it("returns true for valid TeamActivity object", () => {
      const valid: TeamActivity = {
        id: "act-123",
        userId: "user-456",
        userName: "Alice",
        action: "terminal_created",
        timestamp: "2026-06-30T10:00:00Z",
      };

      expect(isTeamActivity(valid)).toBe(true);
    });

    it("returns true for TeamActivity with optional fields", () => {
      const withOptionals: TeamActivity = {
        id: "act-789",
        userId: "user-101",
        userName: "Bob",
        action: "comment_added",
        timestamp: "2026-06-30T11:00:00Z",
        terminalId: "term-42",
        terminalName: "Debug Session",
        comment: "Fixed the bug",
        metadata: { branch: "main" },
      };

      expect(isTeamActivity(withOptionals)).toBe(true);
    });

    it("returns false for null", () => {
      expect(isTeamActivity(null)).toBe(false);
    });

    it("returns false for undefined", () => {
      expect(isTeamActivity(undefined)).toBe(false);
    });

    it("returns false for non-object types", () => {
      expect(isTeamActivity("string")).toBe(false);
      expect(isTeamActivity(123)).toBe(false);
      expect(isTeamActivity(true)).toBe(false);
      expect(isTeamActivity([])).toBe(false);
    });

    it("returns false when id is missing", () => {
      const missing = {
        userId: "user-456",
        userName: "Alice",
        action: "terminal_created",
        timestamp: "2026-06-30T10:00:00Z",
      };

      expect(isTeamActivity(missing)).toBe(false);
    });

    it("returns false when userId is missing", () => {
      const missing = {
        id: "act-123",
        userName: "Alice",
        action: "terminal_created",
        timestamp: "2026-06-30T10:00:00Z",
      };

      expect(isTeamActivity(missing)).toBe(false);
    });

    it("returns false when userName is missing", () => {
      const missing = {
        id: "act-123",
        userId: "user-456",
        action: "terminal_created",
        timestamp: "2026-06-30T10:00:00Z",
      };

      expect(isTeamActivity(missing)).toBe(false);
    });

    it("returns false when action is missing", () => {
      const missing = {
        id: "act-123",
        userId: "user-456",
        userName: "Alice",
        timestamp: "2026-06-30T10:00:00Z",
      };

      expect(isTeamActivity(missing)).toBe(false);
    });

    it("returns false when timestamp is missing", () => {
      const missing = {
        id: "act-123",
        userId: "user-456",
        userName: "Alice",
        action: "terminal_created",
      };

      expect(isTeamActivity(missing)).toBe(false);
    });

    it("returns false when required field has wrong type", () => {
      const wrongType = {
        id: 123, // Should be string
        userId: "user-456",
        userName: "Alice",
        action: "terminal_created",
        timestamp: "2026-06-30T10:00:00Z",
      };

      expect(isTeamActivity(wrongType)).toBe(false);
    });

    it("accepts all valid TeamActivityAction types", () => {
      const actions: Array<TeamActivity["action"]> = [
        "terminal_created",
        "terminal_shared",
        "comment_added",
        "agent_spawned",
        "agent_completed",
        "task_assigned",
        "task_completed",
      ];

      actions.forEach((action) => {
        const activity = {
          id: "act-123",
          userId: "user-456",
          userName: "Alice",
          action,
          timestamp: "2026-06-30T10:00:00Z",
        };

        expect(isTeamActivity(activity)).toBe(true);
      });
    });
  });
});
