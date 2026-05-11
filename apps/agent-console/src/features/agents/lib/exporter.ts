/**
 * Active_Path → Markdown / JSON exporters + side-effectful blob download
 * helper (Req 13.3, Design §New lib modules → exporter.ts).
 *
 * Pure serialisers are deterministic and total. `downloadBlob` is the only
 * side-effectful export; it is a no-op in SSR / no-DOM environments.
 */

import type { ConversationNode } from "../../../stores/workspaceStore";

/**
 * Serialise the Active_Path into a Markdown document. Each node renders as:
 *
 *   ### {role}
 *
 *   {content}
 *
 *   ---
 *
 * Role is lower-cased for display. An empty path collapses to a single
 * header line marker.
 */
export function exportMarkdown(activePath: ConversationNode[]): string {
  if (activePath.length === 0) {
    return "# (empty conversation)\n";
  }
  let out = "";
  for (const node of activePath) {
    out += `### ${node.role.toLowerCase()}\n\n${node.content}\n\n---\n\n`;
  }
  return out;
}

/**
 * Serialise the Active_Path into pretty-printed JSON. An empty path returns
 * `"[]\n"` so downloads always produce a non-empty file.
 */
export function exportJson(activePath: ConversationNode[]): string {
  if (activePath.length === 0) {
    return "[]\n";
  }
  return `${JSON.stringify(activePath, null, 2)}\n`;
}

/**
 * Trigger a browser file download for the given string contents. Creates a
 * Blob, resolves an object URL, synthesises a hidden `<a>` element, clicks
 * it, and cleans up. In SSR / non-DOM environments (no `document`, no
 * `URL.createObjectURL`), this is a defensive no-op.
 */
export function downloadBlob(
  contents: string,
  filename: string,
  mime: string,
): void {
  if (typeof document === "undefined") {
    return;
  }
  if (typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
    return;
  }
  const blob = new Blob([contents], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
