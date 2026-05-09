import type { ConversationArtifact, ConversationNode } from "../../stores/workspaceStore";

const FENCE_PATTERN = /```([\w.+-]*)\n([\s\S]*?)```/g;
const MAX_TEXT_ARTIFACT_CHARS = 12000;

export function extractArtifactsFromNode(node: ConversationNode): ConversationArtifact[] {
  const textArtifacts = extractArtifactsFromText(node.content, node.id, node.run_id);
  const toolArtifacts = node.tool_calls.flatMap((call, index) =>
    extractArtifactsFromToolOutput(call, `${node.id}-tool-${index}`, node.run_id),
  );
  return [...textArtifacts, ...toolArtifacts];
}

export function extractArtifactsFromText(
  content: string,
  sourceId: string,
  runId?: string,
): ConversationArtifact[] {
  const artifacts: ConversationArtifact[] = [];
  let fenceIndex = 0;
  for (const match of content.matchAll(FENCE_PATTERN)) {
    const language = normalizeLanguage(match[1]);
    const body = match[2].trim();
    if (!body) continue;
    artifacts.push({
      id: `${sourceId}-fence-${fenceIndex}`,
      name: `assistant-${fenceIndex + 1}.${extensionForLanguage(language)}`,
      artifact_type: artifactTypeForContent(body, language),
      status: "extracted",
      content: body,
      run_id: runId,
    });
    fenceIndex += 1;
  }

  const stripped = content.replace(FENCE_PATTERN, "").trim();
  if (!stripped) return artifacts;

  const json = parseJson(stripped);
  if (json !== null) {
    artifacts.push({
      id: `${sourceId}-json`,
      name: "assistant.json",
      artifact_type: "json",
      status: "extracted",
      content: json,
      run_id: runId,
    });
    return artifacts;
  }

  if (isUnifiedDiff(stripped)) {
    artifacts.push({
      id: `${sourceId}-diff`,
      name: "assistant.diff",
      artifact_type: "diff",
      status: "extracted",
      content: stripped,
      run_id: runId,
    });
    return artifacts;
  }

  if (artifacts.length === 0 && stripped.length >= 80) {
    artifacts.push({
      id: `${sourceId}-text`,
      name: "assistant.txt",
      artifact_type: "text",
      status: "extracted",
      content: stripped.slice(0, MAX_TEXT_ARTIFACT_CHARS),
      run_id: runId,
    });
  }

  return artifacts;
}

export function extractArtifactsFromToolOutput(
  call: Record<string, unknown>,
  sourceId: string,
  runId?: string,
): ConversationArtifact[] {
  const output = asRecord(call.output_json);
  if (!output) return [];

  const explicit = extractExplicitToolArtifacts(output, sourceId, runId);
  if (explicit.length > 0) return explicit;

  const candidates = [output.content, output.text, output.diff, output.json, output.result, output.preview];
  const artifacts: ConversationArtifact[] = [];
  candidates.forEach((candidate, index) => {
    if (typeof candidate === "string") {
      artifacts.push(...extractArtifactsFromText(candidate, `${sourceId}-output-${index}`, runId));
      return;
    }
    if (candidate && typeof candidate === "object") {
      artifacts.push({
        id: `${sourceId}-output-${index}-json`,
        name: `tool-output-${index + 1}.json`,
        artifact_type: "json",
        status: "extracted",
        content: candidate,
        run_id: runId,
      });
    }
  });
  return artifacts;
}

function extractExplicitToolArtifacts(
  output: Record<string, unknown>,
  sourceId: string,
  runId?: string,
): ConversationArtifact[] {
  const rawArtifacts = Array.isArray(output.artifacts) ? output.artifacts : [];
  return rawArtifacts.flatMap((raw, index) => {
    const artifact = asRecord(raw);
    if (!artifact) return [];
    const content = artifact.content ?? artifact.preview ?? artifact.data;
    return [
      {
        id: String(artifact.id ?? `${sourceId}-artifact-${index}`),
        name: String(artifact.name ?? `tool-artifact-${index + 1}`),
        artifact_type: artifactType(artifact.artifact_type ?? artifact.type, content),
        status: String(artifact.status ?? "extracted"),
        content,
        run_id: typeof artifact.run_id === "string" ? artifact.run_id : runId,
      },
    ];
  });
}

function normalizeLanguage(value: string | undefined) {
  return (value ?? "text").trim().toLowerCase() || "text";
}

function extensionForLanguage(language: string) {
  if (["json", "jsonc"].includes(language)) return "json";
  if (["diff", "patch"].includes(language)) return "diff";
  if (["ts", "tsx", "js", "jsx", "py", "md", "yaml", "yml", "sh", "sql"].includes(language)) return language;
  return "txt";
}

function artifactTypeForContent(
  content: string,
  language: string,
): ConversationArtifact["artifact_type"] {
  if (["json", "jsonc"].includes(language) || parseJson(content) !== null) return "json";
  if (["diff", "patch"].includes(language) || isUnifiedDiff(content)) return "diff";
  if (["text", "markdown", "md"].includes(language)) return "text";
  return "code";
}

function artifactType(value: unknown, content: unknown): ConversationArtifact["artifact_type"] {
  if (value === "code" || value === "json" || value === "diff" || value === "chart" || value === "text") {
    return value;
  }
  if (typeof content === "string") return artifactTypeForContent(content, "text");
  return "json";
}

function isUnifiedDiff(content: string) {
  return /^diff --git /m.test(content) || (/^---\s+/m.test(content) && /^\+\+\+\s+/m.test(content));
}

function parseJson(content: string): unknown | null {
  if (!/^[\[{]/.test(content.trim())) return null;
  try {
    return JSON.parse(content);
  } catch {
    return null;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
