/**
 * Slash command primitives for the Workspace composer (v3 / Req 5).
 *
 * Pure, side-effect-free module. Components:
 *   - `SLASH_COMMANDS` — hard-coded command registry.
 *   - `parseSlashCommand(draft)` — classify a composer draft into
 *     `none | matching | confirmed`. TOTAL; never throws.
 *   - `filterCommandsByPrefix(prefix)` — case-insensitive prefix match over
 *     primary name + aliases.
 *   - `replaceSlashPrefix(draft, name)` — rewrite the first `/xxx` segment
 *     with `/{name} `, keeping any trailing user text intact.
 *
 * Properties (see Req 9 of v3 spec):
 *   - P12: `parseSlashCommand` is TOTAL for any input string.
 *   - P13: `parseSlashCommand` is a pure function of its input (idempotent
 *     when called twice with the same string).
 *   - P14: when `kind === "confirmed"`, `restDraft` never retains the
 *     `/command` prefix; args are trimmed.
 */

export type SlashCommandName =
  | "plan"
  | "run"
  | "chat"
  | "goal"
  | "compress"
  | "pin"
  | "clear"
  | "model"
  | "mcp"
  | "tool"
  | "search"
  | "help";

export type SlashCommand = {
  /** Canonical command identifier. */
  name: SlashCommandName;
  /** Alternative triggers (e.g. `"Harness Agent"` for `plan`). Lower-case only. */
  aliases: string[];
  /** Whether this command expects a single textual argument (e.g. `/tool <name>`). */
  needsArgs: boolean;
  /** Bilingual description surfaced in `SlashCommandMenu`. */
  zh: string;
  en: string;
  /** Literal primary trigger used in the menu (e.g. `"/plan"`). */
  trigger: string;
};

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    name: "plan",
    aliases: ["Harness Agent", "plan-md"],
    needsArgs: false,
    zh: "生成 Markdown 规划",
    en: "Generate a markdown plan",
    trigger: "/plan",
  },
  {
    name: "run",
    aliases: ["act", "execute"],
    needsArgs: false,
    zh: "创建执行运行",
    en: "Create an executable run",
    trigger: "/run",
  },
  {
    name: "chat",
    aliases: [],
    needsArgs: false,
    zh: "切回 Chat 模式",
    en: "Switch back to Chat mode",
    trigger: "/chat",
  },
  {
    name: "goal",
    aliases: ["pursue"],
    needsArgs: false,
    zh: "切换到追求目标模式",
    en: "Switch to Goal pursuit mode",
    trigger: "/goal",
  },
  {
    name: "compress",
    aliases: ["compact", "context"],
    needsArgs: false,
    zh: "压缩当前上下文",
    en: "Compress current context",
    trigger: "/compress",
  },
  {
    name: "pin",
    aliases: [],
    needsArgs: false,
    zh: "固定上一条消息",
    en: "Pin the last message",
    trigger: "/pin",
  },
  {
    name: "clear",
    aliases: [],
    needsArgs: false,
    zh: "清空当前对话",
    en: "Clear current conversation",
    trigger: "/clear",
  },
  {
    name: "model",
    aliases: [],
    needsArgs: false,
    zh: "打开模型选择器",
    en: "Open model picker",
    trigger: "/model",
  },
  {
    name: "mcp",
    aliases: ["plugins"],
    needsArgs: false,
    zh: "列出当前可用 MCP",
    en: "List available MCP tools",
    trigger: "/mcp",
  },
  {
    name: "tool",
    aliases: [],
    needsArgs: true,
    zh: "插入 @tool 提及（/tool <name>）",
    en: "Insert @tool mention (/tool <name>)",
    trigger: "/tool",
  },
  {
    name: "search",
    aliases: [],
    needsArgs: false,
    zh: "打开会话搜索",
    en: "Open conversation search",
    trigger: "/search",
  },
  {
    name: "help",
    aliases: [],
    needsArgs: false,
    zh: "打开快捷键帮助",
    en: "Open keyboard shortcuts",
    trigger: "/help",
  },
];

export type SlashParseResult =
  | { kind: "none" }
  | {
      kind: "matching";
      prefix: string;
      candidates: SlashCommand[];
    }
  | {
      kind: "confirmed";
      command: SlashCommand;
      args: string;
      restDraft: string;
    };

/**
 * Case-insensitive prefix match over each command's primary name plus aliases.
 * Empty prefix yields the full registry, preserving declaration order.
 */
export function filterCommandsByPrefix(prefix: string): SlashCommand[] {
  const p = prefix.toLowerCase();
  if (p.length === 0) return [...SLASH_COMMANDS];
  return SLASH_COMMANDS.filter((cmd) => {
    if (cmd.name.toLowerCase().startsWith(p)) return true;
    for (const alias of cmd.aliases) {
      if (alias.toLowerCase().startsWith(p)) return true;
    }
    return false;
  });
}

/**
 * Locate a command whose primary name or alias matches `head` exactly
 * (case-insensitive). Returns `undefined` when nothing matches.
 */
function resolveExactCommand(head: string): SlashCommand | undefined {
  const h = head.toLowerCase();
  for (const cmd of SLASH_COMMANDS) {
    if (cmd.name.toLowerCase() === h) return cmd;
    for (const alias of cmd.aliases) {
      if (alias.toLowerCase() === h) return cmd;
    }
  }
  return undefined;
}

/**
 * Classify `draft` into `none | matching | confirmed`.
 *
 * Rules (v3 Req 5):
 *   - Draft with no leading `/` or containing a newline → `none`.
 *   - Leading `/` with head that does not map to any command → `matching`
 *     (surfaces the candidate list so the user can continue typing).
 *   - Leading `/` with head that matches a command:
 *       * If the command takes no args, classification is `confirmed` only
 *         when the user has typed a trailing space (i.e. `"/run "` or
 *         `"/run <extra>"`); a bare `"/run"` remains `matching` so the
 *         user can still navigate the menu with ArrowUp/Down. The Enter key
 *         handler in the composer explicitly dispatches the highlighted
 *         command even on `matching` results.
 *       * If the command takes args and args are non-empty, classification
 *         is `confirmed` with args trimmed.
 *       * If the command takes args but args are empty, classification is
 *         `matching` (keep the menu open pending the user typing a value).
 *   - `restDraft` is always an empty string on `confirmed` because slash
 *     commands always consume the entire draft (Req 5.5 / P14).
 */
export function parseSlashCommand(draft: string): SlashParseResult {
  // TOTAL guard: coerce non-string input to string defensively; callers pass
  // strings but fast-check can feed bizarre inputs.
  if (typeof draft !== "string") return { kind: "none" };
  if (draft.length === 0) return { kind: "none" };
  if (draft.charAt(0) !== "/") return { kind: "none" };
  if (draft.indexOf("\n") !== -1) return { kind: "none" };

  // Strip leading '/' and split at the first whitespace run. `args` preserves
  // the remainder verbatim so we can trim it later.
  const body = draft.slice(1);
  const spaceIdx = firstSpaceIndex(body);
  const head = spaceIdx === -1 ? body : body.slice(0, spaceIdx);
  const rawArgs = spaceIdx === -1 ? "" : body.slice(spaceIdx + 1);
  const hasTrailingSpace = spaceIdx !== -1;

  const exact = resolveExactCommand(head);
  if (exact !== undefined) {
    if (exact.needsArgs) {
      const args = rawArgs.trim();
      if (args.length > 0) {
        return { kind: "confirmed", command: exact, args, restDraft: "" };
      }
      return {
        kind: "matching",
        prefix: head,
        candidates: [exact],
      };
    }
    // No-args command.
    if (hasTrailingSpace) {
      return {
        kind: "confirmed",
        command: exact,
        args: "",
        restDraft: "",
      };
    }
    // Bare `/run` without trailing space — keep the menu open but highlight
    // this single candidate so Enter still dispatches.
    return {
      kind: "matching",
      prefix: head,
      candidates: [exact],
    };
  }

  return {
    kind: "matching",
    prefix: head,
    candidates: filterCommandsByPrefix(head),
  };
}

/**
 * Rewrite the first `/xxx` segment of `draft` with `"/{name} "`, keeping any
 * trailing user text intact. Used by Tab-to-autocomplete in the composer.
 *
 * Examples:
 *   replaceSlashPrefix("/pl",          "plan") -> "/plan "
 *   replaceSlashPrefix("/ru",          "run") -> "/run "
 *   replaceSlashPrefix("/pl curl",     "tool") -> "/tool curl"
 *   replaceSlashPrefix("/tool ",       "tool") -> "/tool "
 *   replaceSlashPrefix("",             "plan") -> "/plan "
 */
export function replaceSlashPrefix(
  draft: string,
  name: SlashCommandName,
): string {
  if (typeof draft !== "string") return `/${name} `;
  if (draft.length === 0 || draft.charAt(0) !== "/") return `/${name} `;
  const body = draft.slice(1);
  const spaceIdx = firstSpaceIndex(body);
  if (spaceIdx === -1) return `/${name} `;
  const tail = body.slice(spaceIdx + 1);
  return `/${name} ${tail}`;
}

/**
 * Finds the index of the first ASCII space, tab, or non-breaking space.
 * Newlines are NOT counted because `parseSlashCommand` already rejects
 * drafts containing `\n`.
 */
function firstSpaceIndex(body: string): number {
  for (let i = 0; i < body.length; i += 1) {
    const ch = body.charAt(i);
    if (ch === " " || ch === "\t") return i;
  }
  return -1;
}
