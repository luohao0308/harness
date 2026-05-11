/**
 * Outside-click (and Escape-key) listener used by every popover / overlay in
 * Workspace v2.
 *
 * - Requirement 6.1: popovers (Context / Pin / ToolMention / ModelPicker /
 *   Export menu) must collapse when the user clicks outside of them.
 * - Requirement 14.4: overlays (SearchOverlay, ShortcutOverlay) share the same
 *   closing semantics — outside click OR `Escape` key dismisses them.
 *
 * Design reference: design.md §New hooks → `useOutsideClick`.
 *
 * Behaviour:
 *   - When `enabled !== false` the hook binds three `document`-level listeners:
 *     `mousedown`, `touchstart` and `keydown`. Any pointer event whose target
 *     is outside of `ref.current` triggers `onOutside()`. A `keydown` of the
 *     `Escape` key triggers `onOutside()` unconditionally.
 *   - When `enabled === false` no listeners are bound (this lets callers
 *     cheaply gate the hook based on popover `open` state).
 *   - All listeners are removed in the `useEffect` cleanup to avoid leaks.
 *   - `ref.current === null` is treated as "outside" (the popover is not
 *     mounted yet), which matches the conservative close-on-click contract
 *     used by Radix / Headless UI.
 */

import { useEffect } from "react";
import type { RefObject } from "react";

export function useOutsideClick<T extends HTMLElement>(
  ref: RefObject<T | null>,
  onOutside: () => void,
  enabled: boolean = true,
): void {
  useEffect(() => {
    if (enabled === false) {
      return;
    }

    const handlePointer = (event: MouseEvent | TouchEvent): void => {
      const element = ref.current;
      if (element === null) {
        onOutside();
        return;
      }
      const target = event.target;
      if (target instanceof Node && element.contains(target)) {
        return;
      }
      onOutside();
    };

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        onOutside();
      }
    };

    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("touchstart", handlePointer);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("touchstart", handlePointer);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [ref, onOutside, enabled]);
}
