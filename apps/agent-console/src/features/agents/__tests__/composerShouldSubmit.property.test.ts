// Feature: agent-workspace-chat-refine, Property 3: Composer submit truth table
import { describe, it, expect } from "vitest";
import fc from "fast-check";

import { composerShouldSubmit } from "../components/ChatComposer";

/**
 * Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 11.1, 11.6
 *
 * Property 3 — composerShouldSubmit returns true iff ALL of:
 *   event.isComposing === false
 *   event.keyCode !== 229
 *   event.key === "Enter"
 *   event.shiftKey === false
 *   draft.trim().length >= 1
 *   isStreaming === false
 */

type KeyEvent = {
  isComposing: boolean;
  keyCode: number;
  key: string;
  shiftKey: boolean;
  metaKey: boolean;
  ctrlKey: boolean;
};

function buildEvent(input: KeyEvent): KeyboardEvent {
  // Node's test environment does not expose the DOM `KeyboardEvent` class,
  // and `composerShouldSubmit` only reads the five scalar fields listed in
  // the truth table. We construct a plain record and adapt it through the
  // `unknown` ladder to stay type-safe without `any` / `ts-expect-error`.
  return input as unknown as KeyboardEvent;
}

const keyEventGen: fc.Arbitrary<KeyEvent> = fc.record({
  isComposing: fc.boolean(),
  keyCode: fc.oneof(
    fc.constant(13),
    fc.constant(229),
    fc.integer({ min: 0, max: 255 }),
  ),
  key: fc.oneof(
    fc.constant("Enter"),
    fc.constant(" "),
    fc.constant("a"),
    fc.constant("Escape"),
    fc.constant("Tab"),
    fc.string({ maxLength: 3 }),
  ),
  shiftKey: fc.boolean(),
  metaKey: fc.boolean(),
  ctrlKey: fc.boolean(),
});

describe("Property 3: Composer submit truth table", () => {
  it("returns true iff all five conditions hold simultaneously", () => {
    fc.assert(
      fc.property(
        keyEventGen,
        fc.string({ maxLength: 16 }),
        fc.boolean(),
        (rawEvent, draft, isStreaming) => {
          const event = buildEvent(rawEvent);
          const expected =
            rawEvent.isComposing === false &&
            rawEvent.keyCode !== 229 &&
            rawEvent.key === "Enter" &&
            rawEvent.shiftKey === false &&
            draft.trim().length >= 1 &&
            isStreaming === false;
          expect(composerShouldSubmit(event, draft, isStreaming)).toBe(expected);
        },
      ),
      { numRuns: 500 },
    );
  });

  it("plain Enter with non-empty draft and idle stream submits", () => {
    const event = buildEvent({
      isComposing: false,
      keyCode: 13,
      key: "Enter",
      shiftKey: false,
      metaKey: false,
      ctrlKey: false,
    });
    expect(composerShouldSubmit(event, "hello", false)).toBe(true);
  });

  it("Shift+Enter never submits", () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 16 }).filter((s) => s.trim().length > 0),
        fc.boolean(),
        (draft, isStreaming) => {
          const event = buildEvent({
            isComposing: false,
            keyCode: 13,
            key: "Enter",
            shiftKey: true,
            metaKey: false,
            ctrlKey: false,
          });
          expect(composerShouldSubmit(event, draft, isStreaming)).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it("IME composition (keyCode 229) suppresses submission", () => {
    const event = buildEvent({
      isComposing: false,
      keyCode: 229,
      key: "Enter",
      shiftKey: false,
      metaKey: false,
      ctrlKey: false,
    });
    expect(composerShouldSubmit(event, "你好", false)).toBe(false);
  });
});
