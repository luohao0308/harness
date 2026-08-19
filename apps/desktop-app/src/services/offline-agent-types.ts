export type DesktopOfflineAgentStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'WAITING_APPROVAL'
  | 'INTERRUPTED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export type DesktopOfflineAgentToolName =
  | 'workspace.list_files'
  | 'workspace.read_text'
  | 'workspace.write_text'

export type DesktopOfflineAgentToolRequest = {
  name: DesktopOfflineAgentToolName
  input: Record<string, unknown>
}

export type DesktopOfflineAgentFileBaseline = {
  path: string
  exists: boolean
  sha256: string | null
  mtimeMs: number | null
  sizeBytes: number | null
}

export type DesktopOfflineAgentFileProposal = {
  sha256: string
  sizeBytes: number
}

export type DesktopOfflineAgentRun = {
  id: string
  prompt: string
  result: string | null
  status: DesktopOfflineAgentStatus
  modelSource: 'deterministic-local' | 'local-model' | null
  modelProvider: string
  modelName: string
  modelRequested: boolean
  fallbackReason: string | null
  errorMessage: string | null
  toolRequest: DesktopOfflineAgentToolRequest | null
  pendingApprovalId: string | null
  createdAt: string
  updatedAt: string
  startedAt: string | null
  completedAt: string | null
  syncRevision: number
}

export type DesktopOfflineAgentEvent = {
  id: string
  runId: string
  sequence: number
  eventType: string
  payload: Record<string, unknown>
  actorType: 'system' | 'user'
  createdAt: string
}

export type DesktopOfflineAgentModelCall = {
  id: string
  runId: string
  modelProvider: string
  modelName: string
  status: 'SUCCESS' | 'FAILED' | 'CANCELLED'
  durationMs: number
  requestSha256: string
  responseText: string | null
  errorMessage: string | null
  createdAt: string
}

export type DesktopOfflineAgentToolCall = {
  id: string
  runId: string
  toolName: DesktopOfflineAgentToolName
  riskLevel: 'LOW' | 'HIGH'
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'DENIED' | 'CANCELLED'
  input: Record<string, unknown>
  output: Record<string, unknown>
  errorMessage: string | null
  durationMs: number
  createdAt: string
  updatedAt: string
}

export type DesktopOfflineAgentApproval = {
  id: string
  runId: string
  toolCallId: string
  toolName: DesktopOfflineAgentToolName
  riskLevel: 'HIGH'
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED'
  reason: string
  request: Record<string, unknown>
  target: DesktopOfflineAgentFileBaseline | null
  proposal: DesktopOfflineAgentFileProposal | null
  decision: Record<string, unknown>
  createdAt: string
  decidedAt: string | null
}

export type DesktopOfflineAgentSnapshot = {
  schemaVersion: 1
  run: DesktopOfflineAgentRun
  events: DesktopOfflineAgentEvent[]
  modelCalls: DesktopOfflineAgentModelCall[]
  toolCalls: DesktopOfflineAgentToolCall[]
  approvals: DesktopOfflineAgentApproval[]
}

export type DesktopOfflineAgentRunInput = {
  prompt: string
  useLocalModel?: boolean
  toolRequest?: DesktopOfflineAgentToolRequest | null
}
